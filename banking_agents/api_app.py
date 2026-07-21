from __future__ import annotations

"""Versioned JSON API for browser and approved API clients.

Run locally with:
    python -m uvicorn banking_agents.api_app:app --host 127.0.0.1 --port 8001

The active persistence remains the local JSON/SQLite demo adapters. Production
must use durable authentication, PostgreSQL, object storage, and bank-approved
credit-bureau/KYC integrations.
"""

from dataclasses import asdict
from datetime import date
import os
from pathlib import Path
import re
import secrets
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .audit import AuditLog
from .agent_settings import AgentSettingsStore
from .auth_service import AuthenticatedUser, authenticate_local_user
from .automation_agent import OperationsAutomationAgent
from .chat_agent import BankingSupportChatAgent
from .chatbot_training import LocalChatbotTrainingDatabase
from .credit_bureau_agent import (
    CreditBureauDecisionAgent,
    LocalCreditBureauDatabase,
    LocalCreditBureauProvider,
)
from .dormancy_agent import DormancyAgent
from .loan_agent import LoanExceptionAgent
from .loan_origination import LoanOriginationService
from .local_models import MODEL_COMPONENTS
from .models import Account, DormancyStatus, LoanApplication
from .policy import PolicyConfig
from .progression import loan_progress
from .repository import LocalRepository
from .training_store import ModelTrainingDatabase
from .user_registry import UserRegistry


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


UserRole = Literal["CUSTOMER", "LOAN", "CREDIT", "COMPLIANCE", "ADMIN"]
SignupRole = Literal["CUSTOMER", "LOAN", "CREDIT", "COMPLIANCE"]
SUPPORTED_DOCUMENT_TYPES = {
    "PAN",
    "AADHAAR",
    "ADDRESS_PROOF",
    "BANK_STATEMENT",
    "INCOME_PROOF",
    "SALARY_SLIP",
    "EMPLOYMENT_PROOF",
    "INCOME_TAX_RETURN",
    "PROPERTY_DOCUMENT",
    "BUSINESS_REGISTRATION",
    "FINANCIAL_STATEMENT",
}


class LoginRequest(StrictRequest):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    user_type: UserRole


class SignupRequest(StrictRequest):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    user_type: SignupRole


class LoanCreateRequest(StrictRequest):
    applicant_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(min_length=7, max_length=20, pattern=r"^[0-9+() -]+$")
    residential_address: str = Field(min_length=1, max_length=500)
    loan_product: Literal["PERSONAL", "HOME", "BUSINESS"] = "PERSONAL"
    requested_amount: float = Field(gt=0)
    tenure_months: int = Field(gt=0)
    loan_purpose: str = Field(min_length=1, max_length=500)
    employment_type: Literal["SALARIED", "SELF_EMPLOYED", "BUSINESS_OWNER"]
    employer_name: str = Field(default="", max_length=160)
    monthly_income: float = Field(gt=0)
    pan_for_bureau_lookup: str = Field(
        min_length=10,
        max_length=10,
        pattern=r"^[A-Za-z]{5}[0-9]{4}[A-Za-z]$",
    )
    credit_bureau_consent: bool
    consent_version: Literal["CREDIT_BUREAU_CONSENT_V1"] = "CREDIT_BUREAU_CONSENT_V1"
    uploaded_document_types: list[str] = Field(default_factory=list, max_length=20)


class ApprovalDecisionRequest(StrictRequest):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(default="", max_length=1000)


class ReactivationRequest(StrictRequest):
    kyc_confirmed: bool


class CreditReviewRequest(StrictRequest):
    reason: str = Field(min_length=10, max_length=1000)
    bureau_dispute_reference: str = Field(default="", max_length=100)


class DormancyRunRequest(StrictRequest):
    account_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    jurisdiction: str = Field(default="IN-RBI-DEA", min_length=1, max_length=64)
    balance: float = Field(ge=0)
    last_customer_activity: date
    as_of_date: date


class AutomationRunRequest(StrictRequest):
    as_of_date: date


class ChatMessageRequest(StrictRequest):
    message: str = Field(min_length=1, max_length=1000)


class AgentSettingRequest(StrictRequest):
    enabled: bool


class ApiRuntime:
    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory
        self.tokens: dict[str, AuthenticatedUser] = {}

    def services(self):
        repository = LocalRepository(self.data_directory / "state.json")
        audit = AuditLog(self.data_directory / "audit.jsonl")
        policy = PolicyConfig()
        loan_agent = LoanExceptionAgent(repository, audit, policy, exception_db_path=self.data_directory / "loan_exception_cases.sqlite3")
        dormancy_agent = DormancyAgent(repository, audit, policy, dormancy_db_path=self.data_directory / "dormancy_cases.sqlite3")
        bureau_database = LocalCreditBureauDatabase(self.data_directory / "credit_bureau.sqlite3")
        bureau_agent = CreditBureauDecisionAgent(
            repository,
            audit,
            policy,
            LocalCreditBureauProvider(bureau_database, policy),
        )
        origination = LoanOriginationService(repository, loan_agent, bureau_agent)
        return repository, audit, loan_agent, dormancy_agent, origination

    def agent_settings(self) -> AgentSettingsStore:
        return AgentSettingsStore(self.data_directory / "agent_settings.json")

    def require_agent_enabled(self, model_key: str) -> None:
        if not self.agent_settings().is_enabled(model_key):
            raise HTTPException(
                503,
                "This AI agent is disabled by an Administrator. The dependent workflow is unavailable until it is re-enabled.",
            )


def create_app(data_directory: str | Path | None = None) -> FastAPI:
    data_path = Path(data_directory) if data_directory else Path(os.getenv("BANKING_DATA_DIR", Path.cwd() / "data"))
    runtime = ApiRuntime(data_path)
    security = HTTPBearer(auto_error=False)
    api = FastAPI(
        title="Banking Operations AI API",
        version="1.0.0",
        description="Role-scoped local API for loan exceptions, credit-bureau routing, dormant accounts, approvals, and model governance.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    configured_origins = os.getenv(
        "BANKING_CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000",
    )
    cors_origins = [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip() and origin.strip() != "*"
    ]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @api.middleware("http")
    async def request_context(request: Request, call_next):
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied_request_id
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied_request_id)
            else f"req_{uuid4().hex}"
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @api.exception_handler(HTTPException)
    async def http_problem(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error.detail, str) else "Request could not be completed."
        return JSONResponse(
            status_code=error.status_code,
            media_type="application/problem+json",
            content={
                "type": f"https://local.banking-ai/problems/http-{error.status_code}",
                "title": detail,
                "status": error.status_code,
                "detail": detail,
                "requestId": request.state.request_id,
            },
        )

    @api.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, error: RequestValidationError):
        # Do not echo Pydantic's `input` field: request bodies contain PAN,
        # contact information, and credentials.
        violations = [
            {
                "location": [str(part) for part in item.get("loc", ())],
                "message": item.get("msg", "Invalid value."),
                "type": item.get("type", "validation_error"),
            }
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "https://local.banking-ai/problems/request-validation",
                "title": "Request validation failed.",
                "status": 422,
                "detail": "One or more request fields are invalid.",
                "violations": violations,
                "requestId": request.state.request_id,
            },
        )

    def response(request: Request, data: Any, status: int = 200) -> JSONResponse:
        return JSONResponse(status_code=status, content={"data": data, "meta": {"requestId": request.state.request_id}})

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> AuthenticatedUser:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(401, "Bearer token is required.")
        current = runtime.tokens.get(credentials.credentials)
        if current is None:
            raise HTTPException(401, "Token is invalid or expired.")
        return current

    def allow(current: AuthenticatedUser, *roles: str) -> None:
        if current.role not in roles:
            raise HTTPException(403, "The authenticated role is not authorised for this action.")

    def owned_loan(repository: LocalRepository, application_id: str, current: AuthenticatedUser) -> LoanApplication:
        allow(current, "CUSTOMER", "LOAN", "CREDIT", "ADMIN")
        try:
            loan = repository.get_loan(application_id)
        except KeyError as error:
            raise HTTPException(404, "Loan application was not found.") from error
        if current.role == "CUSTOMER" and loan.submitted_by != current.username:
            raise HTTPException(404, "Loan application was not found.")
        return loan

    def scoped_approvals(current: AuthenticatedUser, items: list[Any]) -> list[Any]:
        if current.role == "CREDIT":
            return [item for item in items if item.required_role == "credit.manager"]
        if current.role == "COMPLIANCE":
            return [item for item in items if item.required_role == "compliance.officer"]
        if current.role == "LOAN":
            return [
                item
                for item in items
                if item.kind
                in {
                    "LOAN_DEVIATION",
                    "CREDIT_SCORE_REVIEW",
                    "CREDIT_BUREAU_UNAVAILABLE",
                    "CREDIT_RECONSIDERATION",
                }
            ]
        return items

    @api.get("/api/v1/health", tags=["System"])
    def health(request: Request):
        return response(request, {"status": "ok", "apiVersion": "v1", "persistence": "local-json-sqlite-demo"})

    @api.post("/api/v1/auth/login", tags=["Authentication"])
    def login(payload: LoginRequest, request: Request):
        current = authenticate_local_user(data_path, payload.username, payload.password, payload.user_type)
        if current is None:
            raise HTTPException(401, "Username, password, or selected user type is invalid.")
        token = secrets.token_urlsafe(40)
        runtime.tokens[token] = current
        return response(
            request,
            {
                "accessToken": token,
                "tokenType": "Bearer",
                "user": asdict(current),
                "expiresIn": None,
                "localDemoWarning": "In-memory tokens are lost when the API restarts.",
            },
        )

    @api.post("/api/v1/auth/signup", tags=["Authentication"])
    def signup(payload: SignupRequest, request: Request):
        try:
            status = UserRegistry(data_path / "users.json").register(
                payload.username,
                payload.password,
                payload.display_name,
                payload.email,
                payload.user_type,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return response(request, {"status": status}, status=201)

    @api.post("/api/v1/auth/logout", tags=["Authentication"])
    def logout(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        if credentials:
            runtime.tokens.pop(credentials.credentials, None)
        return response(request, {"loggedOut": True})

    @api.get("/api/v1/me", tags=["Authentication"])
    def me(request: Request, current: AuthenticatedUser = Depends(identity)):
        return response(request, asdict(current))

    @api.get("/api/v1/me/dashboard", tags=["Dashboards"])
    def dashboard(request: Request, current: AuthenticatedUser = Depends(identity)):
        repository, _, _, _, _ = runtime.services()
        loans = repository.list_loans()
        accounts = repository.list_accounts()
        approvals = repository.list_approvals()
        if current.role == "CUSTOMER":
            loans = [item for item in loans if item.submitted_by == current.username]
            accounts = [item for item in accounts if item.customer_id == current.customer_id]
            approvals = []
        elif current.role == "LOAN":
            accounts = []
            approvals = scoped_approvals(current, approvals)
        elif current.role == "CREDIT":
            accounts = []
            approvals = scoped_approvals(current, approvals)
        elif current.role == "COMPLIANCE":
            loans = []
            approvals = scoped_approvals(current, approvals)
        return response(
            request,
            {
                "role": current.role,
                "metrics": {
                    "loanApplications": len(loans),
                    "accounts": len(accounts),
                    "pendingApprovals": sum(item.status == "PENDING" for item in approvals),
                },
                "recentApplications": [asdict(item) for item in loans[-10:]],
                "pendingActions": [asdict(item) for item in approvals if item.status == "PENDING"],
            },
        )

    @api.post("/api/v1/loan-applications", tags=["Loans"])
    def create_loan(payload: LoanCreateRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER")
        runtime.require_agent_enabled("credit_bureau_decision_agent")
        runtime.require_agent_enabled("loan_exception_agent")
        runtime.require_agent_enabled("document_verification_rules")
        if not payload.credit_bureau_consent:
            raise HTTPException(422, "Credit-bureau consent is required before submission.")
        repository, _, _, _, origination = runtime.services()
        application_id = repository.generate_application_id()
        if payload.date_of_birth >= date.today():
            raise HTTPException(422, "date_of_birth must be in the past.")
        normalized_document_types = {name.upper().strip() for name in payload.uploaded_document_types}
        unsupported_document_types = normalized_document_types - SUPPORTED_DOCUMENT_TYPES
        if unsupported_document_types:
            raise HTTPException(422, "One or more uploaded document types are unsupported.")
        evidence = {name: "PENDING" for name in normalized_document_types}
        loan = LoanApplication(
            application_id,
            "MISSING_DOCUMENT",
            loan_product=payload.loan_product.upper(),
            relationship_manager="customer-self-service",
            applicant_name=payload.applicant_name,
            date_of_birth=payload.date_of_birth.isoformat(),
            email=payload.email,
            phone=payload.phone,
            residential_address=payload.residential_address,
            employment_type=payload.employment_type,
            employer_name=payload.employer_name,
            monthly_income=payload.monthly_income,
            declared_income=payload.monthly_income * 12,
            requested_amount=payload.requested_amount,
            tenure_months=payload.tenure_months,
            loan_purpose=payload.loan_purpose,
            document_evidence=evidence,
            submitted_by=current.username,
        )
        try:
            output = origination.submit(
                loan,
                payload.pan_for_bureau_lookup,
                payload.credit_bureau_consent,
                payload.consent_version,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return response(request, asdict(output), status=201)

    @api.get("/api/v1/loan-applications", tags=["Loans"])
    def list_loans(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER", "LOAN", "CREDIT", "ADMIN")
        repository, _, _, _, _ = runtime.services()
        loans = repository.list_loans()
        if current.role == "CUSTOMER":
            loans = [item for item in loans if item.submitted_by == current.username]
        return response(request, [asdict(item) for item in loans])

    @api.get("/api/v1/loan-applications/{application_id}", tags=["Loans"])
    def loan_detail(application_id: str, request: Request, current: AuthenticatedUser = Depends(identity)):
        repository, _, _, _, _ = runtime.services()
        loan = owned_loan(repository, application_id, current)
        return response(
            request,
            {"application": asdict(loan), "progress": [asdict(item) for item in loan_progress(loan.status, loan.exception_code)]},
        )

    @api.post(
        "/api/v1/loan-applications/{application_id}/credit-review-requests",
        tags=["Loans"],
    )
    def request_credit_review(
        application_id: str,
        payload: CreditReviewRequest,
        request: Request,
        current: AuthenticatedUser = Depends(identity),
    ):
        allow(current, "CUSTOMER")
        repository, audit, _, _, _ = runtime.services()
        loan = owned_loan(repository, application_id, current)
        if loan.status != "REJECTED" or loan.credit_score_decision != "REJECTED_LOW_SCORE":
            raise HTTPException(409, "Credit reconsideration is available only for a low-score rejection.")
        from .models import Approval

        approval = repository.create_approval(
            Approval(
                f"APR-{len(repository.list_approvals()) + 1:04d}",
                "CREDIT_RECONSIDERATION",
                loan.application_id,
                "credit.manager",
                {
                    "customer_reason": payload.reason.strip(),
                    "bureau_dispute_reference": payload.bureau_dispute_reference.strip(),
                    "original_credit_decision": loan.credit_score_decision,
                    "score_reference": loan.credit_score_reference,
                },
            )
        )
        audit.write(
            current.username,
            "credit_bureau.reconsideration_requested",
            loan.application_id,
            "PENDING",
            {"approval_id": approval.approval_id},
        )
        return response(request, asdict(approval), status=201)

    @api.post("/api/v1/loan-applications/{application_id}/documents", tags=["Loans"])
    async def upload_document(
        application_id: str,
        request: Request,
        document_type: str = Form(...),
        file: UploadFile = File(...),
        current: AuthenticatedUser = Depends(identity),
    ):
        runtime.require_agent_enabled("baseline_document_provider")
        repository, audit, _, _, _ = runtime.services()
        loan = owned_loan(repository, application_id, current)
        allow(current, "CUSTOMER", "LOAN", "ADMIN")
        normalized_type = document_type.upper().strip()
        if normalized_type not in SUPPORTED_DOCUMENT_TYPES:
            raise HTTPException(422, "Document type is unsupported.")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(422, "Document must be PDF, PNG, or JPG.")
        try:
            content = await file.read(10 * 1024 * 1024 + 1)
        finally:
            await file.close()
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(422, "Document must be non-empty and no larger than 10 MB.")
        signatures_match = {
            ".pdf": content.startswith(b"%PDF-"),
            ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": content.startswith(b"\xff\xd8\xff"),
            ".jpeg": content.startswith(b"\xff\xd8\xff"),
        }
        if not signatures_match[suffix]:
            raise HTTPException(422, "Document content does not match its file extension.")
        safe_application = re.sub(r"[^A-Za-z0-9_-]", "_", application_id)
        target = data_path / "uploads" / safe_application
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{normalized_type}{suffix}").write_bytes(content)
        loan.document_evidence[normalized_type] = "PENDING"
        repository.save_loan(loan)
        audit.write(current.username, "document.uploaded", loan.application_id, "PENDING", {"document_type": normalized_type, "size": len(content)})
        return response(request, {"documentType": normalized_type, "verificationStatus": "PENDING"}, status=201)

    @api.post("/api/v1/loan-applications/{application_id}/run-exception-agent", tags=["Loans"])
    def run_exception(application_id: str, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "LOAN", "ADMIN")
        runtime.require_agent_enabled("loan_exception_agent")
        runtime.require_agent_enabled("document_verification_rules")
        repository, _, loan_agent, _, _ = runtime.services()
        try:
            repository.get_loan(application_id)
        except KeyError as error:
            raise HTTPException(404, "Loan application was not found.") from error
        return response(request, asdict(loan_agent.run(application_id)))

    @api.get("/api/v1/approvals", tags=["Approvals"])
    def approvals(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "LOAN", "CREDIT", "COMPLIANCE", "ADMIN")
        repository, _, _, _, _ = runtime.services()
        items = repository.list_approvals()
        items = scoped_approvals(current, items)
        return response(request, [asdict(item) for item in items])

    @api.post("/api/v1/approvals/{approval_id}/decision", tags=["Approvals"])
    def decide_approval(
        approval_id: str,
        payload: ApprovalDecisionRequest,
        request: Request,
        current: AuthenticatedUser = Depends(identity),
    ):
        allow(current, "CREDIT", "COMPLIANCE", "ADMIN")
        repository, audit, loan_agent, dormancy_agent, origination = runtime.services()
        try:
            approval = repository.get_approval(approval_id)
        except KeyError as error:
            raise HTTPException(404, "Approval was not found.") from error
        role_authority = {"CREDIT": "credit.manager", "COMPLIANCE": "compliance.officer", "ADMIN": approval.required_role}[current.role]
        if approval.required_role != role_authority:
            raise HTTPException(403, f"This approval requires {approval.required_role}.")
        if approval.status != "PENDING":
            raise HTTPException(409, "Approval has already been decided.")
        if approval.kind in {
            "CREDIT_SCORE_REVIEW",
            "CREDIT_BUREAU_UNAVAILABLE",
            "CREDIT_RECONSIDERATION",
            "LOAN_DEVIATION",
        }:
            runtime.require_agent_enabled("loan_exception_agent")
        if approval.kind in {"ACCOUNT_REACTIVATION", "UNCLAIMED_TRANSFER", "CUSTOMER_RECLAIM"}:
            runtime.require_agent_enabled("dormancy_agent")
        decision = payload.decision
        if decision == "REJECTED" and not payload.note.strip():
            raise HTTPException(422, "A decision note is required when rejecting an approval.")
        approval.status = decision
        approval.decision_by = current.username
        approval.decision_note = payload.note
        repository.save_approval(approval)
        audit.write(current.username, "approval.decided", approval.entity_id, decision, {"approval_id": approval_id})
        updated_entity: dict[str, Any] | None = None
        if approval.kind in {"CREDIT_SCORE_REVIEW", "CREDIT_BUREAU_UNAVAILABLE"}:
            updated_entity = asdict(
                origination.continue_after_credit_review(
                    approval.entity_id,
                    decision == "APPROVED",
                    payload.note or "Credit Manager declined continuation.",
                )
            )
        elif approval.kind == "CREDIT_RECONSIDERATION":
            updated_entity = asdict(
                origination.continue_after_credit_review(
                    approval.entity_id,
                    decision == "APPROVED",
                    payload.note or "Credit Manager declined reconsideration.",
                    approved_decision="LOW_SCORE_RECONSIDERATION_APPROVED",
                    rejected_decision="LOW_SCORE_RECONSIDERATION_REJECTED",
                )
            )
        elif approval.kind == "LOAN_DEVIATION":
            if decision == "APPROVED":
                updated_entity = asdict(loan_agent.apply_approved_deviation(approval.entity_id))
            else:
                updated_entity = asdict(
                    loan_agent.reject_application(approval.entity_id, payload.note)
                )
        elif approval.kind == "ACCOUNT_REACTIVATION" and decision == "APPROVED":
            account = repository.get_account(approval.entity_id)
            account.status = DormancyStatus.ACTIVE.value
            account.outreach_sent = False
            account.dormant_on = None
            account.transfer_due_on = None
            account.last_customer_activity = date.today().isoformat()
            repository.save_account(account)
            for pending in repository.list_approvals():
                if (
                    pending.entity_id == account.account_id
                    and pending.kind == "UNCLAIMED_TRANSFER"
                    and pending.status == "PENDING"
                ):
                    pending.status = "REJECTED"
                    pending.decision_by = current.username
                    pending.decision_note = "Cancelled because account reactivation was approved."
                    repository.save_approval(pending)
            audit.write(current.username, "dormancy.account_reactivated", account.account_id, "SUCCESS", {"approval_id": approval_id})
            updated_entity = asdict(account)
        elif approval.kind == "UNCLAIMED_TRANSFER" and decision == "REJECTED":
            account = repository.get_account(approval.entity_id)
            if account.status == DormancyStatus.TRANSFER_PENDING.value:
                account.status = DormancyStatus.DORMANT.value
                repository.save_account(account)
                updated_entity = asdict(account)
        transfers = dormancy_agent.execute_approved_transfers() if decision == "APPROVED" and approval.kind == "UNCLAIMED_TRANSFER" else []
        claims = dormancy_agent.execute_approved_claims() if decision == "APPROVED" and approval.kind == "CUSTOMER_RECLAIM" else []
        return response(
            request,
            {
                "approval": asdict(approval),
                "updatedEntity": updated_entity,
                "executedTransfers": [asdict(item) for item in transfers],
                "executedClaims": [asdict(item) for item in claims],
            },
        )

    @api.get("/api/v1/accounts", tags=["Dormant accounts"])
    def accounts(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER", "COMPLIANCE", "ADMIN")
        repository, _, _, _, _ = runtime.services()
        items = repository.list_accounts()
        if current.role == "CUSTOMER":
            items = [item for item in items if item.customer_id == current.customer_id]
        return response(request, [asdict(item) for item in items])

    @api.post("/api/v1/accounts/{account_id}/reactivation-requests", tags=["Dormant accounts"])
    def request_reactivation(
        account_id: str,
        payload: ReactivationRequest,
        request: Request,
        current: AuthenticatedUser = Depends(identity),
    ):
        allow(current, "CUSTOMER")
        runtime.require_agent_enabled("dormancy_agent")
        repository, audit, _, _, _ = runtime.services()
        try:
            account = repository.get_account(account_id)
        except KeyError as error:
            raise HTTPException(404, "Account was not found.") from error
        if account.customer_id != current.customer_id:
            raise HTTPException(404, "Account was not found.")
        if not payload.kyc_confirmed:
            raise HTTPException(422, "Current KYC confirmation is required.")
        if account.status not in {
            DormancyStatus.OUTREACH.value,
            DormancyStatus.DORMANT.value,
            DormancyStatus.TRANSFER_PENDING.value,
        }:
            raise HTTPException(409, "Only inactive or dormant accounts can be reactivated.")
        from .models import Approval

        approval = repository.create_approval(
            Approval(
                f"APR-{len(repository.list_approvals()) + 1:04d}",
                "ACCOUNT_REACTIVATION",
                account.account_id,
                "compliance.officer",
                {"customer_id": account.customer_id, "current_status": account.status},
            )
        )
        audit.write(current.username, "dormancy.reactivation_requested", account.account_id, "PENDING", {"approval_id": approval.approval_id})
        return response(request, asdict(approval), status=201)

    @api.post("/api/v1/dormancy/cycles", tags=["Dormant accounts"])
    def run_dormancy(payload: DormancyRunRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN")
        runtime.require_agent_enabled("dormancy_agent")
        repository, _, _, dormancy_agent, _ = runtime.services()
        if payload.jurisdiction not in PolicyConfig().dormancy_days_by_jurisdiction:
            raise HTTPException(422, "Jurisdiction is not configured in the active dormancy policy.")
        if payload.last_customer_activity > payload.as_of_date:
            raise HTTPException(422, "last_customer_activity cannot be after as_of_date.")
        account = Account(
            payload.account_id,
            payload.customer_id,
            payload.jurisdiction,
            payload.balance,
            payload.last_customer_activity.isoformat(),
        )
        repository.save_account(account)
        result = next(item for item in dormancy_agent.run(payload.as_of_date) if item.account_id == account.account_id)
        return response(request, asdict(result))

    @api.post("/api/v1/automation/cycles", tags=["Automation"])
    def run_automation(payload: AutomationRunRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "LOAN", "COMPLIANCE", "ADMIN")
        runtime.require_agent_enabled("operations_automation_agent")
        repository, audit, loan_agent, dormancy_agent, _ = runtime.services()
        result = OperationsAutomationAgent(repository, audit, loan_agent, dormancy_agent).run_cycle(payload.as_of_date)
        return response(request, asdict(result))

    @api.post("/api/v1/chat/messages", tags=["Chat assistant"])
    def chat_message(payload: ChatMessageRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        runtime.require_agent_enabled("banking_support_chatbot")
        repository, audit, _, _, _ = runtime.services()
        result = BankingSupportChatAgent(repository).respond(payload.message, current)
        audit.write(
            current.username,
            "chat.assistant_responded",
            f"CHAT-{current.role}",
            result.intent,
            {"source": result.source, "read_only": result.read_only},
        )
        return response(request, result.to_dict())

    @api.get("/api/v1/ai/agents", tags=["AI governance"])
    def agent_settings(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "ADMIN")
        chatbot_training = LocalChatbotTrainingDatabase(data_path / "chatbot_training.sqlite3").status_report()
        return response(
            request,
            {
                "agents": runtime.agent_settings().list_settings(),
                "chatbotTraining": chatbot_training,
            },
        )

    @api.post("/api/v1/ai/agents/{model_key}/settings", tags=["AI governance"])
    def update_agent_setting(
        model_key: str,
        payload: AgentSettingRequest,
        request: Request,
        current: AuthenticatedUser = Depends(identity),
    ):
        allow(current, "ADMIN")
        try:
            setting = runtime.agent_settings().set_enabled(model_key, payload.enabled, current.username)
        except KeyError as error:
            raise HTTPException(404, "AI agent was not found.") from error
        _, audit, _, _, _ = runtime.services()
        audit.write(
            current.username,
            "ai_agent.setting_changed",
            model_key,
            "ENABLED" if payload.enabled else "DISABLED",
            {"fail_closed_when_disabled": setting["fail_closed_when_disabled"]},
        )
        return response(request, setting)

    @api.get("/api/v1/ai/models", tags=["AI governance"])
    def model_registry(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "ADMIN")
        database = ModelTrainingDatabase(data_path / "model_training.sqlite3")
        database.sync_catalog(MODEL_COMPONENTS)
        return response(request, database.status_report())

    api.state.runtime = runtime
    return api


app = create_app()
