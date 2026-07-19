from __future__ import annotations

"""Versioned JSON API for web, Android, and iOS clients.

Run locally with:
    python -m uvicorn banking_agents.api_app:app --host 127.0.0.1 --port 8001

The active persistence remains the local JSON/SQLite demo adapters. Production
must use durable authentication, PostgreSQL, object storage, and bank-approved
credit-bureau/KYC integrations.
"""

from dataclasses import asdict
from datetime import date
import html
import os
from pathlib import Path
import re
import secrets
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .audit import AuditLog
from .auth_service import AuthenticatedUser, authenticate_local_user
from .automation_agent import OperationsAutomationAgent
from .credit_bureau_agent import (
    CreditBureauDecisionAgent,
    CreditScoreUnavailable,
    LocalCreditBureauDatabase,
    LocalCreditBureauProvider,
)
from .dormancy_agent import DormancyAgent
from .loan_agent import LoanExceptionAgent
from .loan_origination import LoanOriginationService
from .local_models import MODEL_COMPONENTS
from .models import Account, LoanApplication
from .policy import PolicyConfig
from .progression import loan_progress
from .repository import LocalRepository
from .training_store import ModelTrainingDatabase
from .user_registry import UserRegistry


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictRequest):
    username: str
    password: str
    user_type: str


class SignupRequest(StrictRequest):
    username: str
    password: str = Field(min_length=10)
    display_name: str
    email: str
    user_type: str


class LoanCreateRequest(StrictRequest):
    applicant_name: str
    date_of_birth: str
    email: str
    phone: str
    residential_address: str
    loan_product: str = "PERSONAL"
    requested_amount: float = Field(gt=0)
    tenure_months: int = Field(gt=0)
    loan_purpose: str
    employment_type: str
    employer_name: str = ""
    monthly_income: float = Field(gt=0)
    pan_for_bureau_lookup: str
    credit_bureau_consent: bool
    consent_version: str = "CREDIT_BUREAU_CONSENT_V1"
    uploaded_document_types: list[str] = Field(default_factory=list)


class ApprovalDecisionRequest(StrictRequest):
    decision: str
    note: str = ""


class ReactivationRequest(StrictRequest):
    kyc_confirmed: bool


class DormancyRunRequest(StrictRequest):
    account_id: str
    customer_id: str
    jurisdiction: str = "IN-RBI-DEA"
    balance: float = Field(ge=0)
    last_customer_activity: str
    as_of_date: str


class AutomationRunRequest(StrictRequest):
    as_of_date: str


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

    @api.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
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
        try:
            loan = repository.get_loan(application_id)
        except KeyError as error:
            raise HTTPException(404, "Loan application was not found.") from error
        if current.role == "CUSTOMER" and loan.submitted_by != current.username:
            raise HTTPException(404, "Loan application was not found.")
        allow(current, "CUSTOMER", "LOAN", "CREDIT", "COMPLIANCE", "ADMIN")
        return loan

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
        elif current.role == "CREDIT":
            approvals = [item for item in approvals if item.required_role == "credit.manager"]
        elif current.role == "COMPLIANCE":
            approvals = [item for item in approvals if item.required_role == "compliance.officer"]
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
        if not payload.credit_bureau_consent:
            raise HTTPException(422, "Credit-bureau consent is required before submission.")
        repository, _, _, _, origination = runtime.services()
        application_id = repository.generate_application_id()
        evidence = {name.upper().strip(): "PENDING" for name in payload.uploaded_document_types}
        loan = LoanApplication(
            application_id,
            "MISSING_DOCUMENT",
            loan_product=payload.loan_product.upper(),
            relationship_manager="customer-self-service",
            applicant_name=payload.applicant_name,
            date_of_birth=payload.date_of_birth,
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
            output = origination.submit(loan, payload.pan_for_bureau_lookup, payload.credit_bureau_consent)
        except CreditScoreUnavailable as error:
            raise HTTPException(422, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return response(request, asdict(output), status=201)

    @api.get("/api/v1/loan-applications", tags=["Loans"])
    def list_loans(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER", "LOAN", "CREDIT", "COMPLIANCE", "ADMIN")
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

    @api.post("/api/v1/loan-applications/{application_id}/documents", tags=["Loans"])
    async def upload_document(
        application_id: str,
        request: Request,
        document_type: str = Form(...),
        file: UploadFile = File(...),
        current: AuthenticatedUser = Depends(identity),
    ):
        repository, audit, _, _, _ = runtime.services()
        loan = owned_loan(repository, application_id, current)
        allow(current, "CUSTOMER", "LOAN", "ADMIN")
        normalized_type = re.sub(r"[^A-Z0-9_]", "_", document_type.upper().strip())
        if not normalized_type:
            raise HTTPException(422, "Document type is required.")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(422, "Document must be PDF, PNG, or JPG.")
        content = await file.read(10 * 1024 * 1024 + 1)
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(422, "Document must be non-empty and no larger than 10 MB.")
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
        required = {"CREDIT": "credit.manager", "COMPLIANCE": "compliance.officer"}.get(current.role)
        if required:
            items = [item for item in items if item.required_role == required]
        return response(request, [asdict(item) for item in items])

    @api.post("/api/v1/approvals/{approval_id}/decision", tags=["Approvals"])
    def decide_approval(
        approval_id: str,
        payload: ApprovalDecisionRequest,
        request: Request,
        current: AuthenticatedUser = Depends(identity),
    ):
        allow(current, "CREDIT", "COMPLIANCE", "ADMIN")
        repository, audit, _, dormancy_agent, _ = runtime.services()
        try:
            approval = repository.get_approval(approval_id)
        except KeyError as error:
            raise HTTPException(404, "Approval was not found.") from error
        role_authority = {"CREDIT": "credit.manager", "COMPLIANCE": "compliance.officer", "ADMIN": approval.required_role}[current.role]
        if approval.required_role != role_authority:
            raise HTTPException(403, f"This approval requires {approval.required_role}.")
        decision = payload.decision.upper()
        if decision not in {"APPROVED", "REJECTED"}:
            raise HTTPException(422, "Decision must be APPROVED or REJECTED.")
        approval.status = decision
        approval.decision_by = current.username
        approval.decision_note = payload.note
        repository.save_approval(approval)
        audit.write(current.username, "approval.decided", approval.entity_id, decision, {"approval_id": approval_id})
        transfers = dormancy_agent.execute_approved_transfers() if decision == "APPROVED" and approval.kind == "UNCLAIMED_TRANSFER" else []
        return response(request, {"approval": asdict(approval), "executedTransfers": [asdict(item) for item in transfers]})

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
        repository, audit, _, _, _ = runtime.services()
        try:
            account = repository.get_account(account_id)
        except KeyError as error:
            raise HTTPException(404, "Account was not found.") from error
        if account.customer_id != current.customer_id:
            raise HTTPException(404, "Account was not found.")
        if not payload.kyc_confirmed:
            raise HTTPException(422, "Current KYC confirmation is required.")
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
        repository, _, _, dormancy_agent, _ = runtime.services()
        account = Account(payload.account_id, payload.customer_id, payload.jurisdiction, payload.balance, payload.last_customer_activity)
        repository.save_account(account)
        try:
            as_of = date.fromisoformat(payload.as_of_date)
        except ValueError as error:
            raise HTTPException(422, "as_of_date must be YYYY-MM-DD.") from error
        result = next(item for item in dormancy_agent.run(as_of) if item.account_id == account.account_id)
        return response(request, asdict(result))

    @api.post("/api/v1/automation/cycles", tags=["Automation"])
    def run_automation(payload: AutomationRunRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "LOAN", "COMPLIANCE", "ADMIN")
        repository, audit, loan_agent, dormancy_agent, _ = runtime.services()
        try:
            as_of = date.fromisoformat(payload.as_of_date)
        except ValueError as error:
            raise HTTPException(422, "as_of_date must be YYYY-MM-DD.") from error
        result = OperationsAutomationAgent(repository, audit, loan_agent, dormancy_agent).run_cycle(as_of)
        return response(request, asdict(result))

    @api.get("/api/v1/ai/models", tags=["AI governance"])
    def model_registry(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "ADMIN")
        database = ModelTrainingDatabase(data_path / "model_training.sqlite3")
        database.sync_catalog(MODEL_COMPONENTS)
        return response(request, database.status_report())

    api.state.runtime = runtime
    return api


app = create_app()
