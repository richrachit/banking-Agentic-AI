"""Local role-based web interface for the banking workflow demo.

Feature connection: this is the main UI entry point. It connects the browser,
role-based forms, the loan agent, the dormancy agent, the repository, and the
audit log into one local workflow experience.
"""
from __future__ import annotations

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
from .agent_settings import AgentSettingsStore
from .auth_service import AuthenticatedUser, authenticate_local_user
from .automation_agent import OperationsAutomationAgent
from .chat_agent import BankingSupportChatAgent
from .chatbot_training import LocalChatbotTrainingDatabase
from .credit_bureau_agent import CreditBureauDecisionAgent, LocalCreditBureauDatabase, LocalCreditBureauProvider
from .dormancy_agent import DormancyAgent
from .loan_agent import LoanExceptionAgent
from .loan_origination import LoanOriginationService
from .local_models import MODEL_COMPONENTS
from .models import Account, Approval, LoanApplication
from .policy import PolicyConfig
from .progression import loan_progress
from .repository import LocalRepository
from .training_store import ModelTrainingDatabase
from .user_registry import UserRegistry
from .models import DormancyStatus, LoanStatus

# role, display name, username, customer ID. This remains an in-memory local
# demo session store; production uses the bank identity provider.
SESSIONS: dict[str, tuple[str, str, str, str]] = {}
CHAT_HISTORY: dict[str, list[tuple[str, str]]] = {}


def field(values: dict[str, list[str]], name: str) -> str:
    return values.get(name, [""])[0].strip()


def services() -> tuple[LocalRepository, AuditLog, LoanExceptionAgent, DormancyAgent]:
    root = Path.cwd() / "data"
    repo = LocalRepository(root / "state.json")
    audit = AuditLog(root / "audit.jsonl")
    policy = PolicyConfig()
    return repo, audit, LoanExceptionAgent(repo, audit, policy), DormancyAgent(repo, audit, policy)


def require_agent_enabled(model_key: str) -> None:
    if not AgentSettingsStore(Path.cwd() / "data" / "agent_settings.json").is_enabled(model_key):
        raise ValueError("This AI agent is disabled by an Administrator. Its dependent workflow is unavailable until re-enabled.")


class BankingAppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            role, name = self._session()
            if role:
                self._dashboard("Ready for input.", role, name)
            else:
                self._home_page()
            return
        if self.path == "/login":
            self._login_page("Sign in to access your workspace.")
            return
        if self.path == "/signup":
            self._signup_page("Create your workspace access.")
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
        if length < 0 or length > 85 * 1024 * 1024:
            self.send_error(413, "Request body is too large.")
            return
        raw = self.rfile.read(length)
        values, files = self._form_data(raw)
        action = field(values, "action")
        if action == "login":
            self._login(field(values, "username"), field(values, "password"), field(values, "user_type"))
            return
        if action == "signup":
            self._signup(values)
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
        if action == "agent_setting":
            self._allow(role, "ADMIN")
            model_key = field(values, "model_key")
            enabled = field(values, "enabled") == "YES"
            setting = AgentSettingsStore(Path.cwd() / "data" / "agent_settings.json").set_enabled(
                model_key, enabled, self._current_username()
            )
            audit.write(
                self._current_username(),
                "ai_agent.setting_changed",
                model_key,
                "ENABLED" if enabled else "DISABLED",
                {"fail_closed_when_disabled": setting["fail_closed_when_disabled"]},
            )
            state = "enabled" if enabled else "disabled"
            return f"{setting['display_name']} is now {state}. Dependent workflows fail closed while disabled."
        if action == "chat_message":
            require_agent_enabled("banking_support_chatbot")
            question = field(values, "message")
            if not question or len(question) > 1000:
                raise ValueError("Chat messages must contain between 1 and 1000 characters.")
            current = AuthenticatedUser(
                self._current_username(),
                role,
                self._session()[1],
                self._current_customer_id(),
            )
            result = BankingSupportChatAgent(repo).respond(question, current)
            token = self._session_token()
            history = CHAT_HISTORY.setdefault(token, [])
            history.extend([("user", question), ("assistant", result.reply)])
            CHAT_HISTORY[token] = history[-12:]
            audit.write(
                current.username,
                "chat.assistant_responded",
                f"CHAT-{current.role}",
                result.intent,
                {"source": result.source, "read_only": result.read_only},
            )
            return "The Banking Support Assistant answered your question."
        if action == "customer_request":
            self._allow(role, "CUSTOMER")
            require_agent_enabled("credit_bureau_decision_agent")
            require_agent_enabled("loan_exception_agent")
            require_agent_enabled("document_verification_rules")
            pan_for_bureau_lookup = field(values, "pan_for_bureau_lookup")
            if field(values, "credit_bureau_consent") != "YES":
                raise ValueError("Explicit credit-bureau consent is required before submission.")
            if not LocalCreditBureauDatabase.pan_pattern.fullmatch(pan_for_bureau_lookup.upper()):
                raise ValueError("PAN format is invalid for the credit-bureau lookup.")
            application_id = repo.generate_application_id()
            loan = LoanApplication(
                application_id, "MISSING_DOCUMENT", loan_product=field(values, "loan_product") or "PERSONAL",
                relationship_manager="customer-self-service", applicant_name=field(values, "applicant_name"),
                date_of_birth=field(values, "date_of_birth"), email=field(values, "email"), phone=field(values, "phone"),
                residential_address=field(values, "residential_address"), employment_type=field(values, "employment_type"),
                employer_name=field(values, "employer_name"), monthly_income=float(field(values, "monthly_income") or 0),
                requested_amount=float(field(values, "requested_amount") or 0), tenure_months=int(field(values, "tenure_months") or 0),
                loan_purpose=field(values, "loan_purpose"), declared_income=float(field(values, "monthly_income") or 0) * 12,
                document_evidence={},
                submitted_by=self._current_username(),
            )
            required = {"Application ID": loan.application_id, "Applicant name": loan.applicant_name, "Date of birth": loan.date_of_birth, "Email": loan.email, "Phone": loan.phone, "Residential address": loan.residential_address, "Employment type": loan.employment_type, "Monthly income": loan.monthly_income, "Requested amount": loan.requested_amount, "Tenure": loan.tenure_months, "Loan purpose": loan.loan_purpose}
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"Complete the required fields: {', '.join(missing)}.")
            loan.document_evidence = self._save_uploaded_documents(application_id, files)
            policy_config = PolicyConfig()
            bureau_database = LocalCreditBureauDatabase(repo.state_path.parent / "credit_bureau.sqlite3")
            bureau_agent = CreditBureauDecisionAgent(repo, audit, policy_config, LocalCreditBureauProvider(bureau_database, policy_config))
            output = LoanOriginationService(repo, loan_agent, bureau_agent).submit(
                loan,
                pan_for_bureau_lookup,
                True,
            )
            return f"Loan request {output.application_id} created. {output.diagnosis}"
        if action == "customer_dormant_request":
            self._allow(role, "CUSTOMER")
            require_agent_enabled("dormancy_agent")
            account = repo.get_account(field(values, "account_id"))
            if not self._current_customer_id() or account.customer_id != self._current_customer_id():
                raise ValueError("Account was not found.")
            if field(values, "kyc_confirmed") != "YES":
                raise ValueError("Confirm KYC information before submitting a reactivation request.")
            if account.status not in {
                DormancyStatus.OUTREACH.value,
                DormancyStatus.DORMANT.value,
                DormancyStatus.TRANSFER_PENDING.value,
            }:
                raise ValueError("Only inactive or dormant accounts can be reactivated.")
            approval = repo.create_approval(Approval(
                approval_id=f"APR-{len(repo.list_approvals()) + 1:04d}", kind="ACCOUNT_REACTIVATION", entity_id=account.account_id,
                required_role="compliance.officer", package={"customer_id": account.customer_id, "current_status": account.status, "request": "Customer requested dormant account reactivation"},
            ))
            audit.write(self._current_username(), "dormancy.reactivation_requested", account.account_id, "PENDING", {"approval_id": approval.approval_id})
            return f"Reactivation request for {account.account_id} submitted. Compliance review is required before the account can be reactivated."
        if action == "loan_input":
            self._allow(role, "LOAN", "ADMIN")
            require_agent_enabled("loan_exception_agent")
            require_agent_enabled("document_verification_rules")
            evidence = self._evidence(field(values, "document_evidence"))
            application_id = field(values, "application_id")
            exception_code = field(values, "exception_code")
            if not application_id or not exception_code:
                raise ValueError("Application ID and exception type are required.")
            try:
                loan = repo.get_loan(application_id)
                loan.exception_code = exception_code
                loan.loan_product = field(values, "loan_product") or loan.loan_product
                loan.requested_documents = self._list(field(values, "requested_documents"))
                loan.documents = self._list(field(values, "documents"))
                loan.document_evidence = evidence
                loan.declared_income = float(field(values, "declared_income") or 0)
                loan.verified_income = float(field(values, "verified_income") or 0)
                loan.relationship_manager = field(values, "relationship_manager") or loan.relationship_manager
            except KeyError:
                loan = LoanApplication(
                    application_id,
                    exception_code,
                    loan_product=field(values, "loan_product") or "PERSONAL",
                    requested_documents=self._list(field(values, "requested_documents")),
                    documents=self._list(field(values, "documents")),
                    document_evidence=evidence,
                    declared_income=float(field(values, "declared_income") or 0),
                    verified_income=float(field(values, "verified_income") or 0),
                    relationship_manager=field(values, "relationship_manager"),
                )
            repo.save_loan(loan)
            output = loan_agent.run(loan.application_id)
            return f"Loan workflow processed: {output.application_id} is {output.status}. {output.diagnosis}"
        if action == "credit_decision":
            self._allow(role, "CREDIT", "ADMIN")
            require_agent_enabled("loan_exception_agent")
            decision = field(values, "decision")
            note = field(values, "note")
            approval = self._decision(
                repo,
                audit,
                field(values, "approval_id"),
                "credit.manager",
                decision,
                note,
                self._current_username(),
            )
            if approval.kind in {"CREDIT_SCORE_REVIEW", "CREDIT_BUREAU_UNAVAILABLE"}:
                policy_config = PolicyConfig()
                bureau_database = LocalCreditBureauDatabase(repo.state_path.parent / "credit_bureau.sqlite3")
                bureau_agent = CreditBureauDecisionAgent(repo, audit, policy_config, LocalCreditBureauProvider(bureau_database, policy_config))
                LoanOriginationService(repo, loan_agent, bureau_agent).continue_after_credit_review(
                    approval.entity_id,
                    decision == "APPROVED",
                    note or "Credit Manager declined continuation.",
                )
            elif approval.kind == "CREDIT_RECONSIDERATION":
                policy_config = PolicyConfig()
                bureau_database = LocalCreditBureauDatabase(repo.state_path.parent / "credit_bureau.sqlite3")
                bureau_agent = CreditBureauDecisionAgent(repo, audit, policy_config, LocalCreditBureauProvider(bureau_database, policy_config))
                LoanOriginationService(repo, loan_agent, bureau_agent).continue_after_credit_review(
                    approval.entity_id,
                    decision == "APPROVED",
                    note or "Credit Manager declined reconsideration.",
                    approved_decision="LOW_SCORE_RECONSIDERATION_APPROVED",
                    rejected_decision="LOW_SCORE_RECONSIDERATION_REJECTED",
                )
            elif approval.kind == "LOAN_DEVIATION":
                if decision == "APPROVED":
                    loan_agent.apply_approved_deviation(approval.entity_id)
                else:
                    loan_agent.reject_application(approval.entity_id, note)
            return f"{approval.approval_id} marked {decision}. The loan workflow was updated."
        if action == "loan_review_action":
            # Feature: dashboard approve/reject/reopen controls for loan applications.
            # Database connection: updates both the loan status and audit trail.
            self._allow(role, "LOAN", "ADMIN")
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
            require_agent_enabled("dormancy_agent")
            jurisdiction = field(values, "jurisdiction")
            last_customer_activity = date.fromisoformat(field(values, "last_customer_activity"))
            as_of = date.fromisoformat(field(values, "as_of_date"))
            account = Account(field(values, "account_id"), field(values, "customer_id"), jurisdiction, float(field(values, "balance") or 0), last_customer_activity.isoformat())
            if not account.account_id or not account.customer_id or not account.jurisdiction:
                raise ValueError("Account ID, customer ID, and jurisdiction are required.")
            if jurisdiction not in PolicyConfig().dormancy_days_by_jurisdiction:
                raise ValueError("Jurisdiction is not configured in the active dormancy policy.")
            if last_customer_activity > as_of:
                raise ValueError("Last customer activity cannot be after the processing date.")
            repo.save_account(account)
            output = next(item for item in dormancy_agent.run(as_of) if item.account_id == account.account_id)
            return f"Dormancy workflow processed: {output.account_id} is {output.status}."
        if action == "compliance_decision":
            self._allow(role, "COMPLIANCE", "ADMIN")
            require_agent_enabled("dormancy_agent")
            decision = field(values, "decision")
            approval = self._decision(
                repo,
                audit,
                field(values, "approval_id"),
                "compliance.officer",
                decision,
                field(values, "note"),
                self._current_username(),
            )
            if approval.kind == "ACCOUNT_REACTIVATION" and decision == "APPROVED":
                account = repo.get_account(approval.entity_id)
                account.status = DormancyStatus.ACTIVE.value
                account.outreach_sent = False
                account.dormant_on = None
                account.transfer_due_on = None
                account.last_customer_activity = date.today().isoformat()
                repo.save_account(account)
                for pending in repo.list_approvals():
                    if pending.entity_id == account.account_id and pending.kind == "UNCLAIMED_TRANSFER" and pending.status == "PENDING":
                        pending.status = "REJECTED"
                        pending.decision_by = self._current_username()
                        pending.decision_note = "Cancelled because account reactivation was approved."
                        repo.save_approval(pending)
            elif approval.kind == "UNCLAIMED_TRANSFER" and decision == "REJECTED":
                account = repo.get_account(approval.entity_id)
                if account.status == DormancyStatus.TRANSFER_PENDING.value:
                    account.status = DormancyStatus.DORMANT.value
                    repo.save_account(account)
            transfer_count = len(dormancy_agent.execute_approved_transfers()) if decision == "APPROVED" else 0
            claim_count = len(dormancy_agent.execute_approved_claims()) if decision == "APPROVED" else 0
            return f"{approval.approval_id} marked {decision}. Executed {transfer_count} transfer(s) and {claim_count} claim(s)."
        if action == "run_automation":
            self._allow(role, "LOAN", "COMPLIANCE", "ADMIN")
            require_agent_enabled("operations_automation_agent")
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
            if not payload or len(payload) > 10 * 1024 * 1024:
                raise ValueError(f"{document_type} must be non-empty and no larger than 10 MB.")
            signatures_match = {
                ".pdf": payload.startswith(b"%PDF-"),
                ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
                ".jpg": payload.startswith(b"\xff\xd8\xff"),
                ".jpeg": payload.startswith(b"\xff\xd8\xff"),
            }
            if not signatures_match[suffix]:
                raise ValueError(f"{document_type} content does not match its file extension.")
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{document_type}{suffix}").write_bytes(payload)
            evidence[document_type] = "PENDING"
        return evidence

    @staticmethod
    def _allow(role: str, *allowed: str) -> None:
        if role not in allowed:
            raise ValueError("Your role is not authorized for this action.")

    @staticmethod
    def _decision(
        repo: LocalRepository,
        audit: AuditLog,
        approval_id: str,
        expected: str,
        decision: str,
        note: str,
        actor: str,
    ) -> Approval:
        approval = repo.get_approval(approval_id)
        if approval.required_role != expected:
            raise ValueError(f"Approval {approval_id} requires {approval.required_role}.")
        if approval.status != "PENDING":
            raise ValueError(f"Approval {approval_id} has already been decided.")
        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError("Choose Approved or Rejected.")
        if decision == "REJECTED" and not note.strip():
            raise ValueError("A decision note is required when rejecting an approval.")
        approval.status, approval.decision_by, approval.decision_note = decision, actor, note
        repo.save_approval(approval); audit.write(actor, "approval.decided", approval.entity_id, decision, {"approval_id": approval_id})
        return approval

    def _session(self) -> tuple[str, str]:
        cookie = SimpleCookie(self.headers.get("Cookie")); item = cookie.get("banking_session")
        session = SESSIONS.get(item.value) if item else None
        return (session[0], session[1]) if session else ("", "")

    def _session_token(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie"))
        item = cookie.get("banking_session")
        return item.value if item and item.value in SESSIONS else ""

    def _current_username(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie")); item = cookie.get("banking_session")
        session = SESSIONS.get(item.value) if item else None
        return session[2] if session else ""

    def _current_customer_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie")); item = cookie.get("banking_session")
        session = SESSIONS.get(item.value) if item else None
        return session[3] if session else ""

    def _login(self, username: str, password: str, user_type: str) -> None:
        authenticated = authenticate_local_user(Path.cwd() / "data", username, password, user_type)
        if not authenticated:
            self._login_page("Invalid username, password, or selected user type.")
            return
        token = secrets.token_urlsafe(32); SESSIONS[token] = (
            authenticated.role,
            authenticated.display_name,
            authenticated.username,
            authenticated.customer_id,
        )
        self.send_response(303); self.send_header("Location", "/"); self.send_header("Set-Cookie", f"banking_session={token}; HttpOnly; SameSite=Lax; Path=/"); self.end_headers()

    def _signup(self, values: dict[str, list[str]]) -> None:
        password = field(values, "password")
        if password != field(values, "confirm_password"):
            self._signup_page("Passwords do not match.")
            return
        try:
            status = UserRegistry(Path.cwd() / "data" / "users.json").register(field(values, "username"), password, field(values, "display_name"), field(values, "email"), field(values, "user_type"))
        except ValueError as error:
            self._signup_page(str(error))
            return
        message = "Your Customer account is active. You can now sign in." if status == "ACTIVE" else "Your bank-user access request has been recorded and awaits administrator approval."
        self._login_page(message)

    def _logout(self) -> None:
        cookie = SimpleCookie(self.headers.get("Cookie")); item = cookie.get("banking_session")
        if item:
            SESSIONS.pop(item.value, None)
            CHAT_HISTORY.pop(item.value, None)
        self.send_response(303); self.send_header("Location", "/login"); self.send_header("Set-Cookie", "banking_session=; Max-Age=0; Path=/"); self.end_headers()

    def _redirect(self, target: str) -> None:
        self.send_response(303); self.send_header("Location", target); self.end_headers()

    def _login_page(self, message: str) -> None:
        self._send(self._render_login_page(message))

    def _home_page(self) -> None:
        page = """<!doctype html><html><head><meta charset='utf-8'><title>Banking Operations AI</title><style>*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',Arial,sans-serif;color:#eff6ff;background:#07162f}.hero{min-height:100vh;overflow:hidden;background:radial-gradient(circle at 14% 18%,#2563eb 0,#102a56 35%,#07162f 72%);position:relative}.hero:after{content:'';position:absolute;width:500px;height:500px;border-radius:50%;background:#22d3ee22;right:-150px;top:90px;filter:blur(8px)}nav{max-width:1200px;margin:auto;padding:24px;display:flex;align-items:center;justify-content:space-between;position:relative;z-index:1}.brand{font-weight:800;letter-spacing:.04em}.nav-actions{display:flex;gap:12px}.btn{display:inline-block;padding:12px 18px;border-radius:12px;text-decoration:none;font-weight:700}.btn-outline{color:#fff;border:1px solid #ffffff55}.btn-primary{color:#fff;background:linear-gradient(135deg,#2563eb,#06b6d4);box-shadow:0 12px 26px #0ea5e955}.wrap{max-width:1200px;margin:auto;padding:64px 24px 90px;position:relative;z-index:1}.tag{display:inline-block;padding:8px 12px;border-radius:999px;background:#ffffff14;border:1px solid #ffffff22;color:#cfe8ff;font-size:.85rem;font-weight:700}.hero-grid{display:grid;grid-template-columns:1.12fr .88fr;gap:48px;align-items:center}.hero h1{font-size:clamp(2.8rem,6vw,5.4rem);line-height:1.02;margin:18px 0}.hero h1 span{color:#67e8f9}.hero p{font-size:1.15rem;line-height:1.7;color:#cbd5e1;max-width:650px}.actions{display:flex;gap:14px;margin-top:28px}.panel{padding:26px;border-radius:24px;background:linear-gradient(145deg,#ffffff18,#ffffff08);border:1px solid #ffffff22;box-shadow:0 28px 70px #0005}.panel h3{margin-top:0}.flow{display:grid;gap:14px}.step{display:flex;gap:14px;align-items:center;padding:13px;border-radius:14px;background:#06132966}.num{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#22d3ee;color:#082f49;font-weight:800}.features{background:#f8fafc;color:#0f172a;padding:78px 24px}.features-inner{max-width:1200px;margin:auto}.features h2{font-size:2rem;margin-top:0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{padding:22px;border-radius:18px;background:#fff;border:1px solid #e2e8f0;box-shadow:0 10px 30px #0f172a0d}.icon{font-size:1.7rem}@media(max-width:850px){.hero-grid,.cards{grid-template-columns:1fr}.hero h1{font-size:3rem}.wrap{padding-top:32px}.actions{flex-wrap:wrap}}</style></head><body><section class='hero'><nav><div class='brand'>BANKING OPERATIONS AI</div><div class='nav-actions'><a class='btn btn-outline' href='/login'>Login</a><a class='btn btn-primary' href='/signup'>Sign up</a></div></nav><div class='wrap'><div class='hero-grid'><div><span class='tag'>AI-assisted · Human-controlled · Audit-ready</span><h1>Turn banking exceptions into <span>confident outcomes.</span></h1><p>A single intelligent workspace for loan applications, document and KYC checks, approval routing, dormant-account reactivation, DEA lifecycle controls, and customer communication.</p><div class='actions'><a class='btn btn-primary' href='/signup'>Create an account</a><a class='btn btn-outline' href='/login'>Sign in to workspace</a></div></div><aside class='panel'><h3>How the workflow moves</h3><div class='flow'><div class='step'><span class='num'>1</span><span>Customer submits application or account request</span></div><div class='step'><span class='num'>2</span><span>AI validates documents, KYC signals, and policy rules</span></div><div class='step'><span class='num'>3</span><span>Teams review only exceptions and approvals</span></div><div class='step'><span class='num'>4</span><span>Every decision is recorded for audit and follow-up</span></div></div></aside></div></div></section><section class='features'><div class='features-inner'><h2>Built for customer trust and operational control</h2><div class='cards'><article class='card'><div class='icon'>⌁</div><h3>Loan exception agent</h3><p>Detects missing documents, verification failures, and policy deviations, then routes only the right work to the right person.</p></article><article class='card'><div class='icon'>◈</div><h3>Dormant-account lifecycle</h3><p>Coordinates outreach, waiting periods, approvals, DEA transfer preparation, and future customer claims.</p></article><article class='card'><div class='icon'>✦</div><h3>Explainable AI controls</h3><p>Shows where AI starts, what it recommends, and where human authority is mandatory for customer money and policy exceptions.</p></article></div></div></section></body></html>"""
        page = page.replace("<head>", "<head><meta name='viewport' content='width=device-width, initial-scale=1'>")
        page = page.replace("</style>", "@media(max-width:980px){.hero-grid{grid-template-columns:1fr;gap:30px}.cards{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){nav{padding:18px;align-items:flex-start;gap:14px}.brand{font-size:.9rem}.nav-actions{gap:8px}.btn{padding:10px 12px}.wrap{padding:34px 18px 56px}.hero h1{font-size:2.55rem}.hero p{font-size:1rem}.actions{flex-direction:column}.actions .btn{text-align:center}.features{padding:52px 18px}.cards{grid-template-columns:1fr}.panel{padding:18px}.step{align-items:flex-start}}</style>")
        self._send(page)

    def _render_login_page(self, message: str) -> str:
        return f"""<!doctype html><html><head><meta charset='utf-8'><title>Sign in | Banking Operations AI</title><style>{self._auth_css()}</style></head><body><main><section class='intro'><span class='pill'>Secure operations hub</span><h1>Every exception resolved with calm confidence.</h1><p>Guide customer requests, loan exceptions, credit approvals, compliance reviews, and automation from one elegant workspace.</p><div class='points'><div class='point'>Customer onboarding and document intake</div><div class='point'>Exception triage and approval routing</div><div class='point'>Auditable agentic automation</div></div></section><section class='form'><h2>Welcome back</h2><p class='msg'>{html.escape(message)}</p><form method='post'><input type='hidden' name='action' value='login'><label>User type<select name='user_type' required><option value='' selected disabled>Select your user type</option><option value='CUSTOMER'>Customer</option><option value='LOAN'>Loan Operations</option><option value='CREDIT'>Credit Manager</option><option value='COMPLIANCE'>Compliance Officer</option><option value='ADMIN'>Administrator</option></select></label><label>Username<input name='username' placeholder='Enter username' required></label><label>Password<input name='password' type='password' placeholder='Enter password' required></label><button>Sign in</button></form><p class='subtle'>New here? <a href='/signup'>Create an account or request bank-user access</a></p></section></main></body></html>"""

    def _signup_page(self, message: str) -> None:
        page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Create account | Banking Operations AI</title><style>{self._auth_css()}</style></head><body><main><section class='intro'><span class='pill'>Join the workspace</span><h1>Start your secure banking journey.</h1><p>Customer accounts are available immediately in this local demo. Internal bank roles are registered as access requests for administrator approval.</p><div class='points'><div class='point'>Role-aware access</div><div class='point'>Protected customer information</div><div class='point'>Auditable workflow access</div></div></section><section class='form'><h2>Create account</h2><p class='msg'>{html.escape(message)}</p><form method='post'><input type='hidden' name='action' value='signup'><label>Full name<input name='display_name' required></label><label>Email<input name='email' type='email' required></label><label>User type<select name='user_type' required><option value='CUSTOMER'>Customer</option><option value='LOAN'>Loan Operations</option><option value='CREDIT'>Credit Manager</option><option value='COMPLIANCE'>Compliance Officer</option></select></label><label>Username<input name='username' required></label><label>Password<input name='password' type='password' minlength='10' required></label><label>Confirm password<input name='confirm_password' type='password' minlength='10' required></label><button>Create account</button></form><p class='subtle'><a href='/login'>Back to sign in</a></p></section></main></body></html>"""
        self._send(page)

    @staticmethod
    def _auth_css() -> str:
        return ":root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#0f172a 0%,#1d4ed8 45%,#0e7490 100%);display:grid;place-items:center;padding:24px;color:#f8fafc}main{width:min(1120px,100%);display:grid;grid-template-columns:1.15fr .85fr;border-radius:28px;overflow:hidden;box-shadow:0 30px 80px rgba(2,6,23,.45)}.intro{padding:56px 46px;background:linear-gradient(140deg,rgba(15,23,42,.95),rgba(30,64,175,.88));display:flex;flex-direction:column;justify-content:center}.intro h1{font-size:2.35rem;line-height:1.1;margin:14px 0 16px}.intro p{line-height:1.7;color:#dbeafe}.pill{display:inline-block;padding:8px 12px;border-radius:999px;background:#ffffff1f;border:1px solid #ffffff2b;width:max-content;font-size:.9rem;font-weight:700}.points{margin-top:26px;display:grid;gap:10px}.point{padding:12px 14px;border-radius:12px;background:#ffffff14}.form{padding:42px 38px;background:#fff;color:#0f172a}.form h2{margin-top:0}.msg{padding:12px 14px;border-radius:12px;background:#eff6ff;color:#1d4ed8;font-weight:600}form{display:grid;gap:10px}label{display:block;font-weight:600;color:#334155}input,select,button{width:100%;padding:13px 14px;border-radius:12px;border:1px solid #cbd5e1;font-size:1rem}button{background:linear-gradient(135deg,#2563eb,#1d4ed8);border:0;color:#fff;font-weight:700;cursor:pointer}.subtle{font-size:.9rem;color:#64748b}.subtle a{color:#2563eb;font-weight:700}@media(max-width:860px){main{grid-template-columns:1fr}.intro,.form{padding:32px}}"

    def _render_loan_detail(self, application_id: str) -> None:
        # Feature: detailed loan application view for operations, credit, compliance, and admin.
        # Database connection: reads the selected loan from data/state.json and its approvals/audit records.
        role, name = self._session()
        if not role:
            self._redirect("/login")
            return
        if role not in {"CUSTOMER", "LOAN", "CREDIT", "ADMIN"}:
            self._send("<html><body>Application not found.</body></html>")
            return
        repo, _, loan_agent, _ = services()
        try:
            loan = repo.get_loan(application_id)
        except KeyError:
            self._send("<html><body>Application not found.</body></html>")
            return
        if role == "CUSTOMER" and loan.submitted_by != self._current_username():
            self._send("<html><body>Application not found.</body></html>")
            return
        evidence_rows = "".join(f"<li><b>{html.escape(document)}</b>: {html.escape(status)}</li>" for document, status in sorted(loan.document_evidence.items())) or "<li>No document evidence recorded.</li>"
        documents_rows = "".join(f"<li>{html.escape(item)}</li>" for item in loan.documents) or "<li>No received documents listed.</li>"
        requested_rows = "".join(f"<li>{html.escape(item)}</li>" for item in loan.requested_documents) or "<li>No requested documents listed.</li>"
        approval_rows = "".join(f"<li>{html.escape(item.approval_id)} — {html.escape(item.status)} — {html.escape(item.required_role)}</li>" for item in repo.list_approvals() if item.entity_id == loan.application_id) or "<li>No approvals for this application.</li>"
        progression_rows = "".join(f"<li><b>{'✓' if stage.completed else '○'} {html.escape(stage.name)}</b> — {html.escape(stage.owner)}{' <span class=ai>AI starts here</span>' if stage.ai_active else ''}</li>" for stage in loan_progress(loan.status, loan.exception_code))
        detail = f"""<!doctype html><html><head><meta charset='utf-8'><title>Loan application {html.escape(application_id)}</title><style>body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:24px;background:#f8fafc;color:#0f172a}}main{{max-width:1000px;margin:0 auto;background:#fff;padding:24px;border-radius:20px;box-shadow:0 10px 35px rgba(15,23,42,0.08)}}h1{{margin-top:0}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px}}.card{{background:#f8fafc;padding:16px;border-radius:12px;margin-top:12px}}ul{{padding-left:18px}}.ai{{background:#dbeafe;color:#1d4ed8;padding:2px 7px;border-radius:999px;font-size:.8em}}a{{color:#2563eb}}</style></head><body><main><h1>{html.escape(application_id)}</h1><p><b>Status:</b> {html.escape(loan.status)}<br><b>Customer:</b> {html.escape(loan.applicant_name or '-')}<br><b>Product:</b> {html.escape(loan.loan_product)}<br><b>Diagnosis:</b> {html.escape(loan.diagnosis or '-')}</p><div class='card'><h3>Application progression</h3><p>The AI agent starts at data and document validation, then continues through fraud, credit, and policy assessment. Human authority remains mandatory for deviations and disbursement.</p><ul>{progression_rows}</ul></div><div class='grid'><div class='card'><h3>Applicant details</h3><ul><li><b>Name:</b> {html.escape(loan.applicant_name or '-')}</li><li><b>Email:</b> {html.escape(loan.email or '-')}</li><li><b>Phone:</b> {html.escape(loan.phone or '-')}</li><li><b>Address:</b> {html.escape(loan.residential_address or '-')}</li><li><b>Income:</b> {html.escape(str(loan.monthly_income))}</li><li><b>Requested amount:</b> {html.escape(str(loan.requested_amount))}</li></ul></div><div class='card'><h3>Document evidence</h3><ul>{evidence_rows}</ul></div></div><div class='card'><h3>Requested documents</h3><ul>{requested_rows}</ul></div><div class='card'><h3>Received documents</h3><ul>{documents_rows}</ul></div><div class='card'><h3>Approvals</h3><ul>{approval_rows}</ul></div><p><a href='/'>Back to dashboard</a></p></main></body></html>"""
        detail = detail.replace(
            "<br><b>Diagnosis:</b>",
            f"<br><b>Credit score:</b> {html.escape(str(loan.credit_score) if loan.credit_score is not None else '-')}"
            f" ({html.escape(loan.credit_score_band)})<br><b>Credit decision:</b> {html.escape(loan.credit_score_decision)}"
            "<br><b>Diagnosis:</b>",
        )
        detail = detail.replace("<head>", "<head><meta name='viewport' content='width=device-width, initial-scale=1'>")
        detail = detail.replace("</style>", "@media(max-width:680px){body{padding:12px}main{padding:18px;border-radius:14px}.grid{grid-template-columns:1fr}.card{padding:14px}}</style>")
        self._send(detail)

    def _chat_panel(self, role: str) -> str:
        history = CHAT_HISTORY.get(self._session_token(), [])
        messages = history or [
            (
                "assistant",
                "Hello. I can explain authorised loan, document, credit-bureau, approval, AI-agent, and dormant-account workflows.",
            )
        ]
        message_rows = "".join(
            f"<div class='chat-row chat-{html.escape(sender)}'><span>{'You' if sender == 'user' else 'Banking Assistant'}</span>"
            f"<p>{html.escape(content)}</p></div>"
            for sender, content in messages
        )
        suggestions = "".join(
            "<form method='post' class='chat-suggestion'>"
            "<input type='hidden' name='action' value='chat_message'>"
            f"<button type='submit' name='message' value='{html.escape(prompt, quote=True)}'>{html.escape(prompt)}</button>"
            "</form>"
            for prompt in BankingSupportChatAgent.suggestions_for(role)[:4]
        )
        return (
            "<style>.chat-card{border-color:#bfdbfe;background:linear-gradient(145deg,#fff,#f8fbff)}"
            ".chat-transcript{display:grid;gap:10px;max-height:360px;overflow:auto;padding:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px}"
            ".chat-row{max-width:82%;padding:11px 13px;border-radius:15px}.chat-row span{display:block;font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}"
            ".chat-row p{margin:0;line-height:1.55}.chat-assistant{background:#dbeafe;color:#1e3a8a}.chat-user{justify-self:end;background:#0f172a;color:#fff}"
            ".chat-suggestions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.chat-suggestion{display:block}.chat-suggestion button{width:auto;padding:8px 11px;background:#fff;color:#1d4ed8;border:1px solid #bfdbfe;box-shadow:none;font-size:.82rem}"
            ".chat-compose{grid-template-columns:1fr auto;align-items:end}.chat-compose button{width:auto;min-width:130px}.chat-boundary{font-size:.82rem;color:#64748b;margin:10px 0 0}"
            "@media(max-width:720px){.chat-row{max-width:95%}.chat-compose{grid-template-columns:1fr}.chat-compose button{width:100%}}</style>"
            "<section class='card chat-card'><div class='card-head'><div><h2>Banking Support Assistant</h2>"
            "<p>Role-aware workflow help using only information you are authorised to view.</p></div>"
            "<span class='badge'>Read only</span></div>"
            f"<div class='chat-transcript'>{message_rows}</div><div class='chat-suggestions'>{suggestions}</div>"
            "<form method='post' class='chat-compose'><input type='hidden' name='action' value='chat_message'>"
            "<label>Ask the assistant<input name='message' maxlength='1000' autocomplete='off' "
            "placeholder='Ask about status, documents, approvals, CIBIL, or dormant accounts' required></label>"
            "<button type='submit'>Send message</button></form>"
            "<p class='chat-boundary'>The assistant cannot submit, approve, reject, verify KYC, change a score, disburse, or move money.</p>"
            "</section>"
        )

    def _dashboard(self, message: str, role: str, name: str) -> None:
        repo, _, loan_agent, dormancy_agent = services()
        approvals = "".join(f"<li>{html.escape(item.approval_id)} — {html.escape(item.kind)} — <b>{html.escape(item.status)}</b></li>" for item in repo.list_approvals()) or "<li>No approvals yet.</li>"
        visible_approvals = repo.list_approvals()
        if role == "CUSTOMER":
            visible_approvals = []
        elif role == "LOAN":
            visible_approvals = [
                item
                for item in visible_approvals
                if item.kind in {
                    "LOAN_DEVIATION",
                    "CREDIT_SCORE_REVIEW",
                    "CREDIT_BUREAU_UNAVAILABLE",
                    "CREDIT_RECONSIDERATION",
                }
            ]
        elif role == "CREDIT":
            visible_approvals = [item for item in visible_approvals if item.required_role == "credit.manager"]
        elif role == "COMPLIANCE":
            visible_approvals = [item for item in visible_approvals if item.required_role == "compliance.officer"]
        approvals = "".join(
            f"<li>{html.escape(item.approval_id)} - {html.escape(item.kind)} - <b>{html.escape(item.status)}</b></li>"
            for item in visible_approvals
        ) or "<li>No approvals yet.</li>"
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
        all_accounts = repo.list_accounts()
        pending_approvals = [item for item in repo.list_approvals() if item.status == "PENDING"]
        if role == "CUSTOMER":
            customer_loans = [item for item in all_loans if item.submitted_by == self._current_username()]
            metrics = [("My loan requests", len(customer_loans)), ("Documents pending", len([item for item in customer_loans if item.status == LoanStatus.AWAITING_CUSTOMER.value])), ("On main journey", len([item for item in customer_loans if item.status == LoanStatus.READY_FOR_MAIN_JOURNEY.value]))]
        elif role == "LOAN":
            metrics = [("Open exceptions", len([item for item in all_loans if item.status in {LoanStatus.HELD.value, LoanStatus.AWAITING_CUSTOMER.value}])), ("Credit decisions", len([item for item in pending_approvals if item.required_role == "credit.manager"])), ("Main journey", len([item for item in all_loans if item.status == LoanStatus.READY_FOR_MAIN_JOURNEY.value]))]
        elif role == "CREDIT":
            metrics = [("My approval queue", len([item for item in pending_approvals if item.required_role == "credit.manager"])), ("Policy deviations", len([item for item in pending_approvals if item.kind == "LOAN_DEVIATION"])), ("Rework cases", len([item for item in all_loans if item.status in {LoanStatus.REJECTED.value, LoanStatus.REOPENED.value}]))]
        elif role == "COMPLIANCE":
            metrics = [("Accounts under review", len([item for item in all_accounts if item.status in {DormancyStatus.OUTREACH.value, DormancyStatus.DORMANT.value}])), ("Transfers pending", len([item for item in all_accounts if item.status == DormancyStatus.TRANSFER_PENDING.value])), ("Compliance approvals", len([item for item in pending_approvals if item.required_role == "compliance.officer"]))]
        else:
            metrics = [("Loan applications", len(all_loans)), ("Dormant accounts", len(all_accounts)), ("Open approvals", len(pending_approvals))]
        metric_html = "".join(
            f"<div class='metric'><div class='metric-label'>{html.escape(label)}</div>"
            f"<div class='metric-value'>{count}</div></div>"
            for label, count in metrics
        )
        sections.append(f"<section class='card'><div class='metric-grid'>{metric_html}</div></section>")
        sections.append(self._chat_panel(role))
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
            customer_loans = [item for item in all_loans if item.submitted_by == self._current_username()]
            customer_rows = "".join(f"<tr><td>{html.escape(item.application_id)}</td><td>{html.escape(item.loan_product)}</td><td>{html.escape(item.status)}</td><td>{html.escape(item.diagnosis or '-')}</td><td><a href='/loan/{html.escape(item.application_id)}' target='_blank'>Track</a></td></tr>" for item in customer_loans) or "<tr><td colspan='5'>No loan requests yet.</td></tr>"
            sections.append(f"<section class='card'><div class='card-head'><div><h2>My applications</h2><p>Track the AI progression, status, and next action for your requests.</p></div><span class='badge'>Customer</span></div><table class='table'><thead><tr><th>Application</th><th>Product</th><th>Status</th><th>Next step</th><th></th></tr></thead><tbody>{customer_rows}</tbody></table></section>")
            sections.append("""<section class='card'><div class='card-head'><div><h2>Dormant account service</h2><p>Request reactivation of an inactive or dormant account. KYC and Compliance review remain mandatory.</p></div><span class='badge'>Account service</span></div><form method='post'><input type='hidden' name='action' value='customer_dormant_request'><div class='grid'><label>Account ID<input name='account_id' placeholder='Account ID' required></label><label>Registered customer ID<input name='customer_id' placeholder='Customer ID' required></label><label>KYC confirmation<select name='kyc_confirmed' required><option value='' selected disabled>Select confirmation</option><option value='YES'>I confirm my KYC details are current</option><option value='NO'>KYC update required</option></select></label></div><button>Request account reactivation</button></form><p style='color:#64748b;margin-bottom:0'>For transferred/unclaimed balances, the request is retained in the audit trail and must be processed through the bank’s claim and compliance workflow.</p></section>""")
            sections[-1] = sections[-1].replace(
                "<label>Registered customer ID<input name='customer_id' placeholder='Customer ID' required></label>",
                "",
            ).replace(
                "Request reactivation of an inactive or dormant account.",
                "Request reactivation of one of your inactive or dormant accounts.",
            )
            sections.append("""<section class='card'><div class='card-head'><div><h2>Loan application</h2><p>Complete your details and submit a new request.</p></div><span class='badge'>Customer</span></div><form method='post' enctype='multipart/form-data'><input type='hidden' name='action' value='customer_request'><div class='grid'><label>Full name<input name='applicant_name' placeholder='Full name' required></label><label>Date of birth<input name='date_of_birth' type='date' required></label><label>Email<input name='email' type='email' placeholder='Email address' required></label><label>Phone<input name='phone' placeholder='Phone number' required></label><label>Residential address<input name='residential_address' placeholder='Residential address' required></label><label>Loan product<select name='loan_product'><option>PERSONAL</option><option>HOME</option><option>BUSINESS</option></select></label><label>Requested amount<input name='requested_amount' type='number' min='1' step='0.01' placeholder='Requested loan amount' required></label><label>Tenure (months)<input name='tenure_months' type='number' min='1' placeholder='Tenure in months' required></label><label>Loan purpose<input name='loan_purpose' placeholder='Purpose of loan' required></label><label>Employment type<select name='employment_type'><option value='' selected disabled>Employment type</option><option>SALARIED</option><option>SELF_EMPLOYED</option><option>BUSINESS_OWNER</option></select></label><label>Employer/business<input name='employer_name' placeholder='Employer or business name'></label><label>Monthly income<input name='monthly_income' type='number' min='1' step='0.01' placeholder='Monthly income' required></label></div><div class='grid'><label>PAN<input name='upload_pan' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Aadhaar<input name='upload_aadhaar' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Address proof<input name='upload_address' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Bank statement<input name='upload_bank' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Income proof<input name='upload_income' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Property document<input name='upload_property' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Business registration<input name='upload_business' type='file' accept='.pdf,.png,.jpg,.jpeg'></label><label>Financial statement<input name='upload_financial' type='file' accept='.pdf,.png,.jpg,.jpeg'></label></div><button>Submit loan request</button></form></section>""")
            sections[-1] = sections[-1].replace(
                "</div><div class='grid'><label>PAN",
                "<label>PAN for credit-bureau lookup<input name='pan_for_bureau_lookup' maxlength='10' pattern='[A-Za-z]{5}[0-9]{4}[A-Za-z]' autocomplete='off' placeholder='PAN is used for lookup and not stored' required></label>"
                "<label style='display:flex;grid-template-columns:auto 1fr;align-items:center;gap:10px'><input name='credit_bureau_consent' type='checkbox' value='YES' style='width:auto' required>"
                "I consent to a purpose-specific credit-bureau enquiry for this loan application.</label></div><div class='grid'><label>PAN",
            )
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
            sections.append(f"""<section class='card'><div class='card-head'><div><h2>Dormant-account case register</h2><p>Latest persisted dormant-account and escheatment cases.</p></div><span class='badge'>Case register</span></div>{dormancy_table}</section>""")
        if role == "ADMIN":
            training_database = ModelTrainingDatabase(Path.cwd() / "data" / "model_training.sqlite3")
            training_database.sync_catalog(MODEL_COMPONENTS)
            model_rows = []
            for component in training_database.status_report()["components"]:
                counts = component["examples"]
                latest_run = component["latest_run"]
                run_status = "Not trainable" if not component["training_supported"] else (latest_run["status"] if latest_run else "Not trained")
                evaluation = latest_run["metrics"].get("evaluation_scope", "-") if latest_run else "-"
                model_rows.append(
                    f"<tr><td>{html.escape(component['display_name'])}</td>"
                    f"<td>{html.escape(component['component_type'])}</td>"
                    f"<td>{counts['positive']} / {counts['negative']}</td>"
                    f"<td>{counts['human_verified']} / {counts['synthetic']}</td>"
                    f"<td>{html.escape(run_status)}</td><td>{html.escape(evaluation)}</td></tr>"
                )
            sections.append(
                "<section class='card'><div class='card-head'><div><h2>AI model and data registry</h2>"
                "<p>Positive/negative labels, training provenance, and latest local model status. Synthetic metrics are development checks only.</p>"
                "</div><span class='badge'>Model governance</span></div>"
                "<table class='table'><thead><tr><th>Component</th><th>Type</th><th>Positive / negative</th>"
                "<th>Human / synthetic</th><th>Status</th><th>Evaluation scope</th></tr></thead><tbody>"
                + "".join(model_rows)
                + "</tbody></table></section>"
            )
            chatbot_status = LocalChatbotTrainingDatabase(
                Path.cwd() / "data" / "chatbot_training.sqlite3"
            ).status_report()
            chatbot_run = chatbot_status["latest_run"]
            chatbot_summary = (
                f"{chatbot_status['sample_count']} curated local examples; "
                f"{chatbot_run['status'].lower() if chatbot_run else 'not trained'}"
            )
            setting_rows = []
            for setting in AgentSettingsStore(Path.cwd() / "data" / "agent_settings.json").list_settings():
                enabled = bool(setting["enabled"])
                status_label = "Enabled" if enabled else "Disabled"
                target = "NO" if enabled else "YES"
                action_label = "Disable" if enabled else "Enable"
                setting_rows.append(
                    "<tr>"
                    f"<td><b>{html.escape(setting['display_name'])}</b><br><small>{html.escape(setting['component_type'])}</small></td>"
                    f"<td><span class='agent-status {'agent-enabled' if enabled else 'agent-disabled'}'>{status_label}</span></td>"
                    f"<td>{html.escape(setting['risk_tier'])}</td>"
                    f"<td><small>{html.escape(setting['authority_boundary'])}</small></td>"
                    "<td><form method='post' class='inline-form'>"
                    "<input type='hidden' name='action' value='agent_setting'>"
                    f"<input type='hidden' name='model_key' value='{html.escape(setting['model_key'], quote=True)}'>"
                    f"<input type='hidden' name='enabled' value='{target}'>"
                    f"<button type='submit' class='{'button-disable' if enabled else 'button-enable'}'>{action_label}</button>"
                    "</form></td></tr>"
                )
            sections.append(
                "<section class='card'><div class='card-head'><div><h2>AI agent controls</h2>"
                "<p>Enable or disable each component. Disabling a workflow component fails its dependent operation closed; it never bypasses a control.</p>"
                f"<p class='chatbot-training'>Chatbot training: {html.escape(chatbot_summary)}. Live chat text is not retained for training.</p>"
                "</div><span class='badge'>Administrator</span></div>"
                "<table class='table'><thead><tr><th>Agent</th><th>Status</th><th>Risk</th><th>Authority boundary</th><th>Control</th></tr></thead><tbody>"
                + "".join(setting_rows)
                + "</tbody></table></section>"
            )
        if role in {"LOAN", "COMPLIANCE", "ADMIN"}:
            sections.append("""<section class='card'><div class='card-head'><div><h2>Agentic AI automation</h2><p>Submit an automated review cycle for open cases.</p></div><span class='badge'>Automation</span></div><form method='post'><input type='hidden' name='action' value='run_automation'><label>Run as of<input name='as_of_date' type='date' required></label><button>Run automated cycle</button></form></section>""")
        page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Banking Operations AI</title><style>:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#f8fafc 0%,#e0f2fe 100%);color:#0f172a}}main{{max-width:1240px;margin:0 auto;padding:24px 20px 40px}}header{{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(135deg,#0f172a 0%,#1d4ed8 100%);color:#fff;padding:24px 28px;border-radius:24px;box-shadow:0 16px 40px rgba(15,23,42,0.18)}}header h1{{margin:0;font-size:1.5rem}}.header-meta{{color:#dbeafe;font-size:.95rem;margin-top:6px}}.logout{{padding:10px 16px;border-radius:999px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.2);color:#fff;font-weight:700;cursor:pointer}}.message{{margin:20px 0 8px;padding:14px 16px;border-radius:14px;background:#dcfce7;color:#166534;border:1px solid #bbf7d0}}.content{{display:grid;gap:18px}}.card{{background:#fff;padding:22px 24px;border-radius:20px;box-shadow:0 10px 35px rgba(15,23,42,0.08);border:1px solid #e2e8f0}}.card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}}.card-head h2{{margin:0;font-size:1.2rem}}.card-head p{{margin:6px 0 0;color:#64748b}}.badge{{padding:7px 10px;border-radius:999px;background:#dbeafe;color:#1d4ed8;font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em}}form{{display:grid;gap:12px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:12px}}label{{display:grid;gap:6px;font-weight:600;color:#334155;font-size:.95rem}}input,select,button{{width:100%;padding:12px 13px;border-radius:12px;border:1px solid #cbd5e1;font-size:1rem}}input:focus,select:focus{{outline:2px solid rgba(37,99,235,0.25);border-color:#2563eb}}button{{background:linear-gradient(135deg,#2563eb,#1d4ed8);border:none;color:#fff;font-weight:700;cursor:pointer;box-shadow:0 10px 24px rgba(37,99,235,0.16)}}button:hover{{transform:translateY(-1px)}}.stacked{{margin-top:8px;padding-top:10px;border-top:1px solid #e2e8f0}}ul{{padding-left:18px;line-height:1.7;color:#334155}}@media (max-width: 860px){{.grid{{grid-template-columns:1fr}}header{{flex-direction:column;align-items:flex-start;gap:12px}}}}</style></head><body><main><header><div><h1>Banking Operations AI</h1><div class='header-meta'>{html.escape(name)} · {html.escape(role)}</div></div><form method='post'><input type='hidden' name='action' value='logout'><button class='logout'>Sign out</button></form></header><div class='message'>{html.escape(message)}</div><div class='content'>{''.join(sections)}<section class='card'><div class='card-head'><div><h2>Approval queue</h2><p>Open approvals routed to the current workflow.</p></div><span class='badge'>Queue</span></div><ul>{approvals}</ul></section></div></main></body></html>"""
        page = page.replace("<head>", "<head><meta name='viewport' content='width=device-width, initial-scale=1'>")
        page = page.replace("</style>", ".metric-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.metric{padding:16px;border-radius:14px;background:linear-gradient(135deg,#eff6ff,#fff);border:1px solid #dbeafe}.metric-label{color:#64748b;font-weight:600}.metric-value{font-size:2rem;font-weight:800;color:#1d4ed8}.table{width:100%;border-collapse:collapse}th,td{padding:11px 10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}th{font-size:.8rem;color:#475569;text-transform:uppercase;letter-spacing:.04em}@media(max-width:960px){.metric-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:720px){main{padding:12px 10px 28px}header{padding:20px;flex-direction:column;align-items:stretch;gap:14px;border-radius:18px}header h1{font-size:1.3rem}.logout{width:100%}.message{margin:14px 0 6px}.card{padding:17px 15px;border-radius:16px}.grid,.metric-grid{grid-template-columns:1fr}.card-head{flex-direction:column}.table{display:block;overflow-x:auto;white-space:nowrap}.inline-form{min-width:260px}}</style>")
        self._send(page)
    def _send(self, page: str) -> None:
        if "name='viewport'" not in page:
            page = page.replace("<head>", "<head><meta name='viewport' content='width=device-width, initial-scale=1'>", 1)
        data = page.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), BankingAppHandler)
    print("Banking app running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
