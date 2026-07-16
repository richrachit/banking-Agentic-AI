"""Local role-based web interface for the banking workflow demo.

Feature connection: this is the main UI entry point. It connects the browser,
role-based forms, the loan agent, the dormancy agent, the repository, and the
audit log into one local workflow experience.
"""
from __future__ import annotations

import hmac
import html
import re
import secrets
from datetime import date
from email import policy
from email.parser import BytesParser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .audit import AuditLog
from .automation_agent import OperationsAutomationAgent
from .dormancy_agent import DormancyAgent
from .loan_agent import LoanExceptionAgent
from .models import Account, LoanApplication
from .policy import PolicyConfig
from .repository import LocalRepository
from .models import LoanStatus

# Local-demo credentials only. Replace with OIDC/SSO, MFA, hashed passwords,
# session expiry, CSRF controls, and centrally audited role assignments.
USERS = {
    "customer": ("customer123", "CUSTOMER", "Customer"),
    "loan.ops": ("ops123", "LOAN", "Loan Operations"),
    "credit.manager": ("credit123", "CREDIT", "Credit Manager"),
    "compliance.officer": ("compliance123", "COMPLIANCE", "Compliance Officer"),
    "admin": ("admin123", "ADMIN", "Administrator"),
}
SESSIONS: dict[str, tuple[str, str]] = {}


def field(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def services() -> tuple[LocalRepository, AuditLog, LoanExceptionAgent, DormancyAgent]:
    root = Path.cwd() / "data"
    repo = LocalRepository(root / "state.json")
    audit = AuditLog(root / "audit.jsonl")
    policy = PolicyConfig()
    return repo, audit, LoanExceptionAgent(repo, audit, policy), DormancyAgent(repo, audit, policy)


class BankingAppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/login":
            self._login_page("Sign in to access your workspace.")
            return
        if self.path.startswith("/loan/"):
            self._render_loan_detail(self.path.split("/", 2)[2])
            return
        role, name = self._session()
        if not role:
            self._redirect("/login")
            return
        self._dashboard("Ready for input.", role, name)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        values, files = self._form_data(raw)
        action = field(values, "action")
        if action == "login":
            self._login(field(values, "username"), field(values, "password"), field(values, "user_type"))
            return
        if action == "logout":
            self._logout()
            return
        role, name = self._session()
        if not role:
            self._redirect("/login")
            return
        try:
            message = self._action(action, values, role, files)
        except (KeyError, ValueError) as error:
            message = f"Input error: {error}"
        self._dashboard(message, role, name)

    def _action(self, action: str, values: dict[str, list[str]], role: str, files: dict[str, tuple[str, bytes]]) -> str:
        repo, audit, loan_agent, dormancy_agent = services()
        if action == "customer_request":
            self._allow(role, "CUSTOMER")
            application_id = repo.generate_application_id()
            loan = LoanApplication(
                application_id, "MISSING_DOCUMENT", loan_product=field(values, "loan_product") or "PERSONAL",
                relationship_manager="customer-self-service", applicant_name=field(values, "applicant_name"),
                date_of_birth=field(values, "date_of_birth"), email=field(values, "email"), phone=field(values, "phone"),
                residential_address=field(values, "residential_address"), employment_type=field(values, "employment_type"),
                employer_name=field(values, "employer_name"), monthly_income=float(field(values, "monthly_income") or 0),
                requested_amount=float(field(values, "requested_amount") or 0), tenure_months=int(field(values, "tenure_months") or 0),
                loan_purpose=field(values, "loan_purpose"), declared_income=float(field(values, "monthly_income") or 0) * 12,
                document_evidence=self._save_uploaded_documents(application_id, files),
            )
            required = {"Application ID": loan.application_id, "Applicant name": loan.applicant_name, "Date of birth": loan.date_of_birth, "Email": loan.email, "Phone": loan.phone, "Residential address": loan.residential_address, "Employment type": loan.employment_type, "Monthly income": loan.monthly_income, "Requested amount": loan.requested_amount, "Tenure": loan.tenure_months, "Loan purpose": loan.loan_purpose}
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"Complete the required fields: {', '.join(missing)}.")
            repo.save_loan(loan)
            output = loan_agent.run(loan.application_id)
            return f"Loan request {output.application_id} created. {output.diagnosis}"
        if action == "loan_input":
            self._allow(role, "LOAN", "ADMIN")
            evidence = self._evidence(field(values, "document_evidence"))
            loan = LoanApplication(field(values, "application_id"), field(values, "exception_code"), loan_product=field(values, "loan_product") or "PERSONAL", requested_documents=self._list(field(values, "requested_documents")), documents=self._list(field(values, "documents")), document_evidence=evidence, declared_income=float(field(values, "declared_income") or 0), verified_income=float(field(values, "verified_income") or 0), relationship_manager=field(values, "relationship_manager"))
            if not loan.application_id or not loan.exception_code:
                raise ValueError("Application ID and exception type are required.")
            repo.save_loan(loan)
            output = loan_agent.run(loan.application_id)
            return f"Loan workflow processed: {output.application_id} is {output.status}. {output.diagnosis}"
        if action == "credit_decision":
            self._allow(role, "CREDIT", "ADMIN")
            return self._decision(repo, audit, field(values, "approval_id"), "credit.manager", field(values, "decision"), field(values, "note"))
        if action == "loan_review_action":
            # Feature: dashboard approve/reject/reopen controls for loan applications.
            # Database connection: updates both the loan status and audit trail.
            self._allow(role, "LOAN", "CREDIT", "COMPLIANCE", "ADMIN")
            application_id = field(values, "application_id")
            action = field(values, "review_action")
            if action == "APPROVE":
                loan_agent.approve_application(application_id, field(values, "review_note") or "Approved by operations review")
                return f"Application {application_id} approved."
            if action == "REJECT":
                loan_agent.reject_application(application_id, field(values, "review_note") or "Rejected by operations review")
                return f"Application {application_id} rejected."
            if action == "REOPEN":
                loan_agent.reopen_application(application_id, field(values, "review_note") or "Reopened for resubmission")
                return f"Application {application_id} reopened."
            raise ValueError("Unsupported review action")
        if action == "account_input":
            self._allow(role, "COMPLIANCE", "ADMIN")
            account = Account(field(values, "account_id"), field(values, "customer_id"), field(values, "jurisdiction"), float(field(values, "balance") or 0), field(values, "last_customer_activity"))
            if not account.account_id or not account.customer_id or not account.jurisdiction:
                raise ValueError("Account ID, customer ID, and jurisdiction are required.")
            repo.save_account(account)
            output = next(item for item in dormancy_agent.run(date.fromisoformat(field(values, "as_of_date"))) if item.account_id == account.account_id)
            return f"Dormancy workflow processed: {output.account_id} is {output.status}."
        if action == "compliance_decision":
            self._allow(role, "COMPLIANCE", "ADMIN")
            message = self._decision(repo, audit, field(values, "approval_id"), "compliance.officer", field(values, "decision"), field(values, "note"))
            return message + (f" Executed {len(dormancy_agent.execute_approved_transfers())} approved transfer(s)." if field(values, "decision") == "APPROVED" else "")
        if action == "run_automation":
            self._allow(role, "LOAN", "COMPLIANCE", "ADMIN")
            output = OperationsAutomationAgent(repo, audit, loan_agent, dormancy_agent).run_cycle(date.fromisoformat(field(values, "as_of_date")))
            return f"Automation completed: {len(output.actions)} action(s); {len(output.pending_human_actions)} pending approval(s)."
        raise ValueError("Unknown action.")

    @staticmethod
    def _list(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _evidence(value: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in value.split(","):
            if not item.strip():
                continue
            if ":" not in item:
                raise ValueError("Use DOCUMENT:STATUS, e.g. PAN:VALID.")
            key, status = item.split(":", 1); result[key.strip()] = status.strip()
        return result

    def _form_data(self, raw: bytes) -> tuple[dict[str, list[str]], dict[str, tuple[str, bytes]]]:
        """Read standard and multipart form submissions using the standard library."""
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return parse_qs(raw.decode(), keep_blank_values=True), {}
        message = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw)
        values: dict[str, list[str]] = {}; files: dict[str, tuple[str, bytes]] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            if filename:
                files[name] = (filename, payload)
            else:
                values.setdefault(name, []).append(payload.decode(part.get_content_charset() or "utf-8"))
        return values, files

    @staticmethod
    def _save_uploaded_documents(application_id: str, files: dict[str, tuple[str, bytes]]) -> dict[str, str]:
        document_fields = {"upload_pan": "PAN", "upload_aadhaar": "AADHAAR", "upload_address": "ADDRESS_PROOF", "upload_bank": "BANK_STATEMENT", "upload_income": "INCOME_PROOF", "upload_property": "PROPERTY_DOCUMENT", "upload_business": "BUSINESS_REGISTRATION", "upload_financial": "FINANCIAL_STATEMENT"}
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", application_id)
        target = Path.cwd() / "data" / "uploads" / safe_id
        evidence: dict[str, str] = {}
        for field_name, document_type in document_fields.items():
            if field_name not in files:
                continue
            filename, payload = files[field_name]
            suffix = Path(filename).suffix.lower()
            if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
                raise ValueError(f"{document_type} must be a PDF, PNG, or JPG file.")
            if len(payload) > 10 * 1024 * 1024:
                raise ValueError(f"{document_type} exceeds the 10 MB file limit.")
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{document_type}{suffix}").write_bytes(payload)
            evidence[document_type] = "PENDING"
        return evidence

    @staticmethod
    def _allow(role: str, *allowed: str) -> None:
        if role not in allowed:
            raise ValueError("Your role is not authorized for this action.")

    @staticmethod
    def _decision(repo: LocalRepository, audit: AuditLog, approval_id: str, expected: str, decision: str, note: str) -> str:
        approval = repo.get_approval(approval_id)
        if approval.required_role != expected:
            raise ValueError(f"Approval {approval_id} requires {approval.required_role}.")
        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError("Choose Approved or Rejected.")
        approval.status, approval.decision_by, approval.decision_note = decision, expected, note
        repo.save_approval(approval); audit.write(expected, "approval.decided", approval.entity_id, decision, {"approval_id": approval_id})
        return f"{approval_id} marked {decision}."

    def _session(self) -> tuple[str, str]:
        cookie = SimpleCookie(self.headers.get("Cookie")); item = cookie.get("banking_session")
        return SESSIONS.get(item.value, ("", "")) if item else ("", "")

    def _login(self, username: str, password: str, user_type: str) -> None:
        user = USERS.get(username)
        if not user or not hmac.compare_digest(password, user[0]) or user[1] != user_type:
            self._login_page("Invalid username, password, or selected user type.")
            return
        token = secrets.token_urlsafe(32); SESSIONS[token] = (user[1], user[2])
        self.send_response(303); self.send_header("Location", "/"); self.send_header("Set-Cookie", f"banking_session={token}; HttpOnly; SameSite=Lax; Path=/"); self.end_headers()

    def _logout(self) -> None:
        cookie = SimpleCookie(self.headers.get("Cookie")); item = cookie.get("banking_session")
        if item: SESSIONS.pop(item.value, None)
        self.send_response(303); self.send_header("Location", "/login"); self.send_header("Set-Cookie", "banking_session=; Max-Age=0; Path=/"); self.end_headers()

    def _redirect(self, target: str) -> None:
        self.send_response(303); self.send_header("Location", target); self.end_headers()

    def _login_page(self, message: str) -> None:
        self._send(self._render_login_page(message))

    @staticmethod
    def _render_login_page(message: str) -> str:
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>Sign in | Banking Operations AI</title><style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#0f172a 0%,#1d4ed8 45%,#0e7490 100%);display:grid;place-items:center;padding:24px;color:#f8fafc}}main{{width:min(1120px,100%);display:grid;grid-template-columns:1.15fr .85fr;border-radius:28px;overflow:hidden;box-shadow:0 30px 80px rgba(2,6,23,0.45);backdrop-filter:blur(12px)}}.intro{{padding:56px 46px;background:linear-gradient(140deg,rgba(15,23,42,0.95),rgba(30,64,175,0.88));display:flex;flex-direction:column;justify-content:center}}.intro h1{{font-size:2.35rem;line-height:1.1;margin:14px 0 16px}}.intro p{{font-size:1rem;line-height:1.7;color:#dbeafe}}.pill{{display:inline-block;padding:8px 12px;border-radius:999px;background:#ffffff1f;border:1px solid #ffffff2b;width:max-content;font-size:.9rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}.points{{margin-top:26px;display:grid;gap:10px}}.point{{padding:12px 14px;border-radius:12px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12)}}.form{{padding:42px 38px;background:#ffffff;color:#0f172a}}.form h2{{margin-top:0;margin-bottom:8px;font-size:1.8rem}}.msg{{margin:14px 0 18px;padding:12px 14px;border-radius:12px;background:#eff6ff;color:#1d4ed8;font-weight:600}}form{{display:grid;gap:10px}}label{{display:block;font-weight:600;font-size:.95rem;color:#334155}}input,select,button{{width:100%;padding:13px 14px;border-radius:12px;border:1px solid #cbd5e1;font-size:1rem}}input:focus,select:focus{{outline:2px solid rgba(37,99,235,0.25);border-color:#2563eb}}button{{background:linear-gradient(135deg,#2563eb,#1d4ed8);border:none;color:#fff;font-weight:700;cursor:pointer;box-shadow:0 10px 24px rgba(37,99,235,0.22)}}button:hover{{transform:translateY(-1px)}}.table{{width:100%;border-collapse:collapse;margin-top:6px}}.table th,.table td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:.95rem}}.table th{{color:#475569;font-weight:700;background:#f8fafc}}.subtle{{font-size:.9rem;color:#64748b;margin-top:6px}}@media (max-width: 860px){{main{{grid-template-columns:1fr}}.intro,.form{{padding:32px}}}}</style></head><body><main><section class='intro'><span class='pill'>Secure operations hub</span><h1>Every exception resolved with calm confidence.</h1><p>Guide customer requests, loan exceptions, credit approvals, compliance reviews, and automation from one elegant workspace.</p><div class='points'><div class='point'>Customer onboarding and document intake</div><div class='point'>Exception triage and approval routing</div><div class='point'>Auditable agentic automation</div><div class='point'>Shared workflow visibility for every role</div></div></section><section class='form'><h2>Welcome back</h2><p class='msg'>{html.escape(message)}</p><form method='post'><input type='hidden' name='action' value='login'><label>User type<select name='user_type' required><option value='' selected disabled>Select your user type</option><option value='CUSTOMER'>Customer</option><option value='LOAN'>Loan Operations</option><option value='CREDIT'>Credit Manager</option><option value='COMPLIANCE'>Compliance Officer</option><option value='ADMIN'>Administrator</option></select></label><label>Username<input name='username' placeholder='Enter username' required></label><label>Password<input name='password' type='password' placeholder='Enter password' required></label><button>Sign in</button><div class='subtle'>Demo credentials: customer / loan.ops / credit.manager / compliance.officer / admin with the password matching the username suffix.</div></form></section></main></body></html>"""

    def _render_loan_detail(self, application_id: str) -> None:
        # Feature: detailed loan application view for operations, credit, compliance, and admin.
        # Database connection: reads the selected loan from data/state.json and its approvals/audit records.
        role, name = self._session()
        if not role:
            self._redirect("/login")
            return
        repo, _, loan_agent, _ = services()
        try:
            loan = repo.get_loan(application_id)
        except KeyError:
            self._send("<html><body>Application not found.</body></html>")
            return
        evidence_rows = "".join(f"<li><b>{html.escape(document)}</b>: {html.escape(status)}</li>" for document, status in sorted(loan.document_evidence.items())) or "<li>No document evidence recorded.</li>"
        documents_rows = "".join(f"<li>{html.escape(item)}</li>" for item in loan.documents) or "<li>No received documents listed.</li>"
        requested_rows = "".join(f"<li>{html.escape(item)}</li>" for item in loan.requested_documents) or "<li>No requested documents listed.</li>"
        approval_rows = "".join(f"<li>{html.escape(item.approval_id)} — {html.escape(item.status)} — {html.escape(item.required_role)}</li>" for item in repo.list_approvals() if item.entity_id == loan.application_id) or "<li>No approvals for this application.</li>"
        detail = f"""<!doctype html><html><head><meta charset='utf-8'><title>Loan application {html.escape(application_id)}</title><style>body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:24px;background:#f8fafc;color:#0f172a}}main{{max-width:1000px;margin:0 auto;background:#fff;padding:24px;border-radius:20px;box-shadow:0 10px 35px rgba(15,23,42,0.08)}}h1{{margin-top:0}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px}}.card{{background:#f8fafc;padding:16px;border-radius:12px;margin-top:12px}}ul{{padding-left:18px}}a{{color:#2563eb}}</style></head><body><main><h1>{html.escape(application_id)}</h1><p><b>Status:</b> {html.escape(loan.status)}<br><b>Customer:</b> {html.escape(loan.applicant_name or '-')}<br><b>Product:</b> {html.escape(loan.loan_product)}<br><b>Diagnosis:</b> {html.escape(loan.diagnosis or '-')}</p><div class='grid'><div class='card'><h3>Applicant details</h3><ul><li><b>Name:</b> {html.escape(loan.applicant_name or '-')}</li><li><b>Email:</b> {html.escape(loan.email or '-')}</li><li><b>Phone:</b> {html.escape(loan.phone or '-')}</li><li><b>Address:</b> {html.escape(loan.residential_address or '-')}</li><li><b>Income:</b> {html.escape(str(loan.monthly_income))}</li><li><b>Requested amount:</b> {html.escape(str(loan.requested_amount))}</li></ul></div><div class='card'><h3>Document evidence</h3><ul>{evidence_rows}</ul></div></div><div class='card'><h3>Requested documents</h3><ul>{requested_rows}</ul></div><div class='card'><h3>Received documents</h3><ul>{documents_rows}</ul></div><div class='card'><h3>Approvals</h3><ul>{approval_rows}</ul></div><p><a href='/'>Back to dashboard</a></p></main></body></html>"""
        self._send(detail)

    def _dashboard(self, message: str, role: str, name: str) -> None:
        repo, _, loan_agent, dormancy_agent = services()
        approvals = "".join(f"<li>{html.escape(item.approval_id)} — {html.escape(item.kind)} — <b>{html.escape(item.status)}</b></li>" for item in repo.list_approvals()) or "<li>No approvals yet.</li>"
        exception_cases = []
        if loan_agent.exception_db is not None:
            for item in loan_agent.exception_db.list_cases(limit=6):
                exception_cases.append(
                    f"<tr><td>{html.escape(item['application_id'])}</td><td>{html.escape(item['exception_code'])}</td><td>{html.escape(item.get('customer_name') or '-')}</td><td>{html.escape(item.get('action') or '-')}</td><td>{html.escape(item.get('created_at') or '-')}</td></tr>"
                )
        if not exception_cases:
            exception_cases.append("<tr><td colspan='5'>No persisted exception cases yet.</td></tr>")
        exception_table = f"<table class='table'><thead><tr><th>Application</th><th>Exception</th><th>Customer</th><th>Action</th><th>Created</th></tr></thead><tbody>{''.join(exception_cases)}</tbody></table>"
        dormancy_cases = []
        if dormancy_agent.dormancy_db is not None:
            for item in dormancy_agent.dormancy_db.list_cases(limit=6):
                dormancy_cases.append(
                    f"<tr><td>{html.escape(item['account_id'])}</td><td>{html.escape(item['customer_id'])}</td><td>{html.escape(str(item['balance']))}</td><td>{html.escape(item['status'])}</td><td>{html.escape(item['created_at'])}</td></tr>"
                )
        if not dormancy_cases:
            dormancy_cases.append("<tr><td colspan='5'>No dormant-account cases yet.</td></tr>")
        dormancy_table = f"<table class='table'><thead><tr><th>Account</th><th>Customer</th><th>Balance</th><th>Status</th><th>Created</th></tr></thead><tbody>{''.join(dormancy_cases)}</tbody></table>"
        sections = []
        all_loans = sorted(repo.list_loans(), key=lambda item: item.application_id, reverse=True)
        pending_rows = []
        review_rows = []
        for loan in all_loans:
            status = loan.status
            if status in {LoanStatus.AWAITING_APPROVAL.value, LoanStatus.AWAITING_CUSTOMER.value, LoanStatus.REJECTED.value, LoanStatus.REOPENED.value}:
                review_rows.append(
                    f"<tr><td>{html.escape(loan.application_id)}</td><td>{html.escape(loan.applicant_name or '-')}</td><td>{html.escape(status)}</td><td>{html.escape(loan.diagnosis or '-')}</td><td><form method='post' class='inline-form'><input type='hidden' name='action' value='loan_review_action'><input type='hidden' name='application_id' value='{html.escape(loan.application_id)}'><input type='hidden' name='review_action' value='REOPEN'><input type='text' name='review_note' placeholder='Reason' style='display:inline-block;width:120px;padding:8px 10px;margin-right:6px;'><button type='submit' style='width:auto;padding:8px 12px;'>Reopen</button></form><form method='post' class='inline-form' style='margin-top:6px;'><input type='hidden' name='action' value='loan_review_action'><input type='hidden' name='application_id' value='{html.escape(loan.application_id)}'><input type='hidden' name='review_action' value='APPROVE'><input type='text' name='review_note' placeholder='Reason' style='display:inline-block;width:120px;padding:8px 10px;margin-right:6px;'><button type='submit' style='width:auto;padding:8px 12px;background:#16a34a;'>Approve</button></form><form method='post' class='inline-form' style='margin-top:6px;'><input type='hidden' name='action' value='loan_review_action'><input type='hidden' name='application_id' value='{html.escape(loan.application_id)}'><input type='hidden' name='review_action' value='REJECT'><input type='text' name='review_note' placeholder='Reason' style='display:inline-block;width:120px;padding:8px 10px;margin-right:6px;'><button type='submit' style='width:auto;padding:8px 12px;background:#dc2626;'>Reject</button></form></td></tr>"
                )
            if status in {LoanStatus.AWAITING_APPROVAL.value, LoanStatus.REJECTED.value}:
                pending_rows.append(
                    f"<tr><td>{html.escape(loan.application_id)}</td><td>{html.escape(loan.applicant_name or '-')}</td><td>{html.escape(status)}</td><td>{html.escape(loan.diagnosis or '-')}</td><td><a href='/loan/{html.escape(loan.application_id)}' target='_blank'>View</a></td></tr>"
                )
        if not review_rows:
            review_rows.append("<tr><td colspan='5'>No applications need review.</td></tr>")
        if not pending_rows:
            pending_rows.append("<tr><td colspan='5'>No pending approvals.</td></tr>")
        review_table = f"<table class='table'><thead><tr><th>Application</th><th>Customer</th><th>Status</th><th>AI diagnosis</th><th>Action</th></tr></thead><tbody>{''.join(review_rows)}</tbody></table>"
        pending_table = f"<table class='table'><thead><tr><th>Application</th><th>Customer</th><th>Status</th><th>AI diagnosis</th><th>View</th></tr></thead><tbody>{''.join(pending_rows)}</tbody></table>"
        if role == "CUSTOMER":
            sections.append("""<section class='card'><div class='card-head'><div><h2>Loan application</h2><p>Complete your details and submit a new request.</p></div><span class='badge'>Customer</span></div><form method='post' enctype='multipart/form-data'><input type='hidden' name='action' value='customer_request'><div class='grid'><label>Full name<input name='applicant_name' placeholder='Full name' required></label><label>Date of birth<input name='date_of_birth' type='date' required></label><label>Email<input name='email' type='email' placeholder='Email address' required></label><label>Phone<input name='phone' placeholder='Phone number' required></label><label>Residential address<input name='residential_address' placeholder='Residential address' required></label><label>Loan product<select name='loan_product'><option>PERSONAL</option><option>HOME</option><option>BUSINESS</option></select></label><label>Requested amount<input name='requested_amount' type='number' min='1' step='0.01' placeholder='Requested loan amount' required></label><label>Tenure (months)<input name='tenure_months' type='number' min='1' placeholder='Tenure in months' required></label><label>Loan purpose<input name='loan_purpose' placeholder='Purpose of loan' required></label><label>Employment type<select name='employment_type'><option value='' selected disabled>Employment type</option><option>SALARIED</option><option>SELF_EMPLOYED</option><option>BUSINESS_OWNER</option></select></label><label>Employer/business<input name='employer_name' placeholder='Employer or business name'></label><label>Monthly income<input name='monthly_income' type='number' min='1' step='0.01' placeholder='Monthly income' required></label></div><div class='grid'><label>PAN<input name='upload_pan' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Aadhaar<input name='upload_aadhaar' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Address proof<input name='upload_address' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Bank statement<input name='upload_bank' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Income proof<input name='upload_income' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Property document<input name='upload_property' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Business registration<input name='upload_business' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Financial statement<input name='upload_financial' type='file' accept='.pdf,.png,.jpg,.jpeg'></label></div><button>Submit loan request</button></form></section>""")
        if role in {"LOAN", "ADMIN"}:
            sections.append("""<section class='card'><div class='card-head'><div><h2>Loan operations</h2><p>Review exceptions, evidence, and work items.</p></div><span class='badge'>Operations</span></div><form method='post'><input type='hidden' name='action' value='loan_input'><div class='grid'><label>Application ID<input name='application_id' placeholder='Application ID' required></label><label>Loan product<select name='loan_product'><option>PERSONAL</option><option>HOME</option><option>BUSINESS</option></select></label><label>Exception code<select name='exception_code'><option>MISSING_DOCUMENT</option><option>VERIFY_TRANSIENT_FAILURE</option><option>INCOME_VARIANCE</option></select></label><label>Document evidence<input name='document_evidence' placeholder='PAN:VALID,AADHAAR:EXPIRED'></label><label>Requested documents<input name='requested_documents' placeholder='Extra required documents'></label><label>Received documents<input name='documents' placeholder='Received documents'></label><label>Relationship manager<input name='relationship_manager' placeholder='Relationship manager'></label><label>Declared income<input name='declared_income' type='number' min='0' placeholder='Declared income'></label><label>Verified income<input name='verified_income' type='number' min='0' placeholder='Verified income'></label></div><button>Process loan exception</button></form></section>""")
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Pending / approval queue</h2><p>Applications waiting on AI review, credit approvals, or re-open steps.</p></div><span class='badge'>Queue</span></div>{pending_table}</section>""")
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Review and reopen queue</h2><p>Applications that are rejected or require reassessment.</p></div><span class='badge'>Review</span></div>{review_table}</section>""")
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Recent exception cases</h2><p>Latest persisted outcomes from the exception platform.</p></div><span class='badge'>Audit trail</span></div>{exception_table}</section>""")
        if role in {"CREDIT", "ADMIN"}:
            sections.append("""<section class='card'><div class='card-head'><div><h2>Credit decision</h2><p>Approve or reject the pending deviation package.</p></div><span class='badge'>Credit</span></div><form method='post'><input type='hidden' name='action' value='credit_decision'><div class='grid'><label>Approval ID<input name='approval_id' placeholder='Approval ID' required></label><label>Decision<select name='decision'><option>APPROVED</option><option>REJECTED</option></select></label><label>Decision note<input name='note' placeholder='Decision note'></label></div><button>Submit decision</button></form></section>""")
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Applications for credit review</h2><p>Applications routed for credit approval or rework.</p></div><span class='badge'>Credit queue</span></div>{pending_table}</section>""")
        if role in {"COMPLIANCE", "ADMIN"}:
            sections.append("""<section class='card'><div class='card-head'><div><h2>Dormant account lifecycle</h2><p>Manage account review, transfer approvals, and compliance actions.</p></div><span class='badge'>Compliance</span></div><form method='post'><input type='hidden' name='action' value='account_input'><div class='grid'><label>Account ID<input name='account_id' placeholder='Account ID' required></label><label>Customer ID<input name='customer_id' placeholder='Customer ID' required></label><label>Jurisdiction<input name='jurisdiction' value='IN-RBI-DEA' required></label><label>Balance<input name='balance' type='number' min='0' step='0.01' placeholder='Balance' required></label><label>Last activity<input name='last_customer_activity' type='date' required></label><label>As of<input name='as_of_date' type='date' required></label></div><button>Run lifecycle</button></form><form method='post' class='stacked'><input type='hidden' name='action' value='compliance_decision'><div class='grid'><label>Approval ID<input name='approval_id' placeholder='Approval ID' required></label><label>Decision<select name='decision'><option>APPROVED</option><option>REJECTED</option></select></label><label>Decision note<input name='note' placeholder='Decision note'></label></div><button>Submit compliance decision</button></form></section>""")
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Applications for compliance review</h2><p>Loan cases that need document review or reopen handling.</p></div><span class='badge'>Compliance queue</span></div>{review_table}</section>""")
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Dormant-account case register</h2><p>Latest persisted dormant-account and escheatment cases.</p></div><span class='badge'>Case register</span></div>{dormancy_table}</section>""")
        if role in {"LOAN", "COMPLIANCE", "ADMIN"}:
            sections.append("""<section class='card'><div class='card-head'><div><h2>Agentic AI automation</h2><p>Submit an automated review cycle for open cases.</p></div><span class='badge'>Automation</span></div><form method='post'><input type='hidden' name='action' value='run_automation'><label>Run as of<input name='as_of_date' type='date' required></label><button>Run automated cycle</button></form></section>""")
        page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Banking Operations AI</title><style>:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#f8fafc 0%,#e0f2fe 100%);color:#0f172a}}main{{max-width:1240px;margin:0 auto;padding:24px 20px 40px}}header{{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,#0f172a 0%,#1d4ed8 100%);color:#fff;padding:24px 28px;border-radius:24px;box-shadow:0 16px 40px rgba(15,23,42,0.18)}}header h1{{margin:0;font-size:1.5rem}}.header-meta{{color:#dbeafe;font-size:.95rem;margin-top:6px}}.logout{{padding:10px 16px;border-radius:999px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.2);color:#fff;font-weight:700;cursor:pointer}}.message{{margin:20px 0 8px;padding:14px 16px;border-radius:14px;background:#dcfce7;color:#166534;border:1px solid #bbf7d0}}.content{{display:grid;gap:18px}}.card{{background:#fff;padding:22px 24px;border-radius:20px;box-shadow:0 10px 35px rgba(15,23,42,0.08);border:1px solid #e2e8f0}}.card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}}.card-head h2{{margin:0;font-size:1.2rem}}.card-head p{{margin:6px 0 0;color:#64748b}}.badge{{padding:7px 10px;border-radius:999px;background:#dbeafe;color:#1d4ed8;font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em}}form{{display:grid;gap:12px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px}}label{{display:grid;gap:6px;font-weight:600;color:#334155;font-size:.95rem}}input,select,button{{width:100%;padding:12px 13px;border-radius:12px;border:1px solid #cbd5e1;font-size:1rem}}input:focus,select:focus{{outline:2px solid rgba(37,99,235,0.25);border-color:#2563eb}}button{{background:linear-gradient(135deg,#2563eb,#1d4ed8);border:none;color:#fff;font-weight:700;cursor:pointer;box-shadow:0 10px 24px rgba(37,99,235,0.16)}}button:hover{{transform:translateY(-1px)}}.stacked{{margin-top:8px;padding-top:10px;border-top:1px solid #e2e8f0}}ul{{padding-left:18px;line-height:1.7;color:#334155}}@media (max-width: 860px){{.grid{{grid-template-columns:1fr}}header{{flex-direction:column;align-items:flex-start;gap:12px}}}}</style></head><body><main><header><div><h1>Banking Operations AI</h1><div class='header-meta'>{html.escape(name)} · {html.escape(role)}</div></div><form method='post'><input type='hidden' name='action' value='logout'><button class='logout'>Sign out</button></form></header><div class='message'>{html.escape(message)}</div><div class='content'>{''.join(sections)}<section class='card'><div class='card-head'><div><h2>Approval queue</h2><p>Open approvals routed to the current workflow.</p></div><span class='badge'>Queue</span></div><ul>{approvals}</ul></section></div></main></body></html>"""
        self._send(page)
    def _send(self, page: str) -> None:
        data = page.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), BankingAppHandler)
    print("Banking app running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
