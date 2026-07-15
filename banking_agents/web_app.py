"""Local role-based web interface for the banking workflow demo."""
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
        page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Sign in | Banking Operations AI</title><style>body{{margin:0;min-height:100vh;font-family:Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 12% 18%,#2563eb,#102a56 42%,#061329);display:grid;place-items:center;color:#eef5ff}}main{{width:min(1000px,92vw);display:grid;grid-template-columns:1.2fr .8fr;border-radius:24px;overflow:hidden;box-shadow:0 28px 70px #0008}}.intro{{padding:58px;background:#ffffff10}}.form{{padding:48px;background:#fff;color:#14213d}}h1{{font-size:39px;line-height:1.12}}input,select,button{{box-sizing:border-box;width:100%;padding:13px;border-radius:9px;margin:8px 0;border:1px solid #cbd5e1}}button{{background:#155eef;border:0;color:#fff;font-weight:700;cursor:pointer}}.msg{{background:#eef4ff;color:#174ea6;padding:10px;border-radius:8px}}.points{{margin-top:26px;padding:20px;border:1px solid #ffffff2e;border-radius:12px;background:#ffffff0b}}.points div{{padding:8px 0;border-bottom:1px solid #ffffff20}}.points div:last-child{{border:0}}</style></head><body><main><section class='intro'><b>BANKING OPERATIONS AI</b><h1>Every exception resolved with confidence.</h1><p>One controlled workspace for customer requests, loan operations, credit approvals, compliance, and agentic automation.</p><div class='points'><div>Customer loan journey</div><div>Exception resolution and document verification</div><div>Controlled approvals and compliance workflows</div><div>Auditable agentic automation</div></div></section><section class='form'><h2>Welcome back</h2><p class='msg'>{html.escape(message)}</p><form method='post'><input type='hidden' name='action' value='login'><label>User type<select name='user_type' required><option value='' selected disabled>Select your user type</option><option value='CUSTOMER'>Customer</option><option value='LOAN'>Loan Operations</option><option value='CREDIT'>Credit Manager</option><option value='COMPLIANCE'>Compliance Officer</option><option value='ADMIN'>Administrator</option></select></label><label>Username<input name='username' autocomplete='username' required></label><label>Password<input name='password' type='password' autocomplete='current-password' required></label><button>Sign in securely</button></form><p style='font-size:12px;color:#64748b'>The selected user type must match the account. Production deployments must use bank SSO and MFA.</p></section></main></body></html>"""
        self._send(page)

    def _dashboard(self, message: str, role: str, name: str) -> None:
        repo, _, _, _ = services()
        approvals = "".join(f"<li>{html.escape(item.approval_id)} — {html.escape(item.kind)} — <b>{html.escape(item.status)}</b></li>" for item in repo.list_approvals()) or "<li>No approvals yet.</li>"
        sections = []
        if role == "CUSTOMER": sections.append("<section><h2>Loan Application</h2><p>Complete your details to submit a loan request. Your application ID is generated automatically after submission.</p><form method='post' enctype='multipart/form-data'><input type='hidden' name='action' value='customer_request'><h3>Personal details</h3><input name='applicant_name' placeholder='Full name' required><input name='date_of_birth' type='date' required><br><input name='email' type='email' placeholder='Email address' required><input name='phone' placeholder='Phone number' required><input name='residential_address' placeholder='Residential address' required><h3>Loan details</h3><select name='loan_product'><option>PERSONAL</option><option>HOME</option><option>BUSINESS</option></select><input name='requested_amount' type='number' min='1' step='0.01' placeholder='Requested loan amount' required><input name='tenure_months' type='number' min='1' placeholder='Tenure in months' required><br><input name='loan_purpose' placeholder='Purpose of loan' required><h3>Employment and income</h3><select name='employment_type'><option value='' selected disabled>Employment type</option><option>SALARIED</option><option>SELF_EMPLOYED</option><option>BUSINESS_OWNER</option></select><input name='employer_name' placeholder='Employer or business name'><input name='monthly_income' type='number' min='1' step='0.01' placeholder='Monthly income' required><h3>Upload documents</h3><label>PAN <input name='upload_pan' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Aadhaar <input name='upload_aadhaar' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><br><label>Address proof <input name='upload_address' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Bank statement <input name='upload_bank' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><br><label>Income proof <input name='upload_income' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Property document (Home loan) <input name='upload_property' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><br><label>Business registration <input name='upload_business' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Financial statement <input name='upload_financial' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><p>Accepted formats: PDF, PNG, JPG. Maximum 10 MB per document. All uploads remain pending until bank verification.</p><button>Submit loan application</button></form></section>")
        if role in {"LOAN", "ADMIN"}: sections.append("<section><h2>Loan Operations</h2><form method='post'><input type='hidden' name='action' value='loan_input'><input name='application_id' placeholder='Application ID' required><select name='loan_product'><option>PERSONAL</option><option>HOME</option><option>BUSINESS</option></select><select name='exception_code'><option>MISSING_DOCUMENT</option><option>VERIFY_TRANSIENT_FAILURE</option><option>INCOME_VARIANCE</option></select><br><input name='document_evidence' placeholder='PAN:VALID,AADHAAR:EXPIRED'><input name='requested_documents' placeholder='Extra required documents'><br><input name='documents' placeholder='Received documents'><input name='relationship_manager' placeholder='Relationship manager'><br><input name='declared_income' type='number' min='0' placeholder='Declared income'><input name='verified_income' type='number' min='0' placeholder='Verified income'><button>Process loan exception</button></form></section>")
        if role in {"CREDIT", "ADMIN"}: sections.append("<section><h2>Credit Decision</h2><form method='post'><input type='hidden' name='action' value='credit_decision'><input name='approval_id' placeholder='Approval ID' required><select name='decision'><option>APPROVED</option><option>REJECTED</option></select><input name='note' placeholder='Decision note'><button>Submit decision</button></form></section>")
        if role in {"COMPLIANCE", "ADMIN"}: sections.append("<section><h2>Dormant Account Lifecycle</h2><form method='post'><input type='hidden' name='action' value='account_input'><input name='account_id' placeholder='Account ID' required><input name='customer_id' placeholder='Customer ID' required><input name='jurisdiction' value='IN-RBI-DEA' required><input name='balance' type='number' min='0' step='0.01' placeholder='Balance' required><label>Last activity <input name='last_customer_activity' type='date' required></label><label>As of <input name='as_of_date' type='date' required></label><button>Run lifecycle</button></form><hr><form method='post'><input type='hidden' name='action' value='compliance_decision'><input name='approval_id' placeholder='Approval ID' required><select name='decision'><option>APPROVED</option><option>REJECTED</option></select><input name='note' placeholder='Decision note'><button>Submit compliance decision</button></form></section>")
        if role in {"LOAN", "COMPLIANCE", "ADMIN"}: sections.append("<section><h2>Agentic AI Automation</h2><form method='post'><input type='hidden' name='action' value='run_automation'><label>Run as of <input name='as_of_date' type='date' required></label><button>Run automated cycle</button></form></section>")
        page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Banking Operations AI</title><style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1120px;margin:32px auto;padding:0 18px;background:#f4f7fb;color:#13233d}}header{{display:flex;justify-content:space-between;align-items:center;background:#102a56;color:#fff;padding:18px 24px;border-radius:14px}}section{{background:#fff;padding:22px;margin:18px 0;border-radius:12px;box-shadow:0 5px 16px #1d35571c}}input,select,button{{padding:10px;margin:6px;width:240px;border:1px solid #cbd5e1;border-radius:7px}}button{{width:auto;background:#155eef;color:#fff;border:0;font-weight:650;cursor:pointer}}.message{{padding:12px;background:#e4f2e8;border-radius:8px}}.role{{color:#b9d2ff;font-size:14px}}</style></head><body><header><div><b>Banking Operations AI</b><div class='role'>{html.escape(name)} · {html.escape(role)}</div></div><form method='post'><input type='hidden' name='action' value='logout'><button>Sign out</button></form></header><p class='message'>{html.escape(message)}</p>{''.join(sections)}<section><h2>Approval Queue</h2><ul>{approvals}</ul></section></body></html>"""
        self._send(page)

    def _send(self, page: str) -> None:
        data = page.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), BankingAppHandler)
    print("Banking app running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
