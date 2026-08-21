from __future__ import annotations

"""Focused API for bank-statement verification and dormant-account lifecycle."""

from dataclasses import asdict
from datetime import date, datetime, timezone
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
from pypdf import PdfReader

from .audit import AuditLog
from .auth_service import AuthenticatedUser, authenticate_local_user
from .bank_statement_agent import BankStatementAnalysisAgent, BankStatementDatabase, StatementHeader, Transaction, VerificationEvidence
from .dormancy_agent import DormancyAgent
from .models import Account, Approval, DormancyStatus
from .policy import PolicyConfig
from .repository import LocalRepository


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


UserRole = Literal["CUSTOMER", "UNDERWRITER", "COMPLIANCE", "ADMIN"]


class LoginRequest(StrictRequest):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    user_type: UserRole


class StatementHeaderRequest(StrictRequest):
    customer_name: str = Field(min_length=1, max_length=120)
    account_number_masked: str = Field(min_length=4, max_length=40)
    ifsc_code: str = Field(default="", max_length=20)
    bank_name: str = Field(min_length=1, max_length=120)
    branch_name: str = Field(default="", max_length=120)
    period_start: date
    period_end: date


class TransactionRequest(StrictRequest):
    transaction_date: date
    narration: str = Field(min_length=1, max_length=1000)
    debit: float = Field(default=0, ge=0)
    credit: float = Field(default=0, ge=0)
    running_balance: float
    reference_number: str = Field(default="", max_length=100)
    transaction_mode: str = Field(default="OTHER", max_length=30)


class EvidenceRequest(StrictRequest):
    consent_id: str = Field(min_length=1, max_length=100)
    consented_at: datetime
    consent_purpose: Literal["INCOME_AND_EMPLOYMENT_VERIFICATION"] = "INCOME_AND_EMPLOYMENT_VERIFICATION"
    source: Literal["DOCUMENT_UPLOAD", "ACCOUNT_AGGREGATOR"] = "DOCUMENT_UPLOAD"
    gst_reported_turnover: float | None = Field(default=None, ge=0)
    itr_reported_income: float | None = Field(default=None, ge=0)
    gst_filing_delays: int = Field(default=0, ge=0)
    itr_filing_delays: int = Field(default=0, ge=0)
    outstanding_tax_demand: float = Field(default=0, ge=0)


class AnalyzeStatementRequest(StrictRequest):
    analysis_id: str = Field(default="", max_length=100)
    customer_id: str = Field(default="", max_length=64)
    header: StatementHeaderRequest
    transactions: list[TransactionRequest] = Field(min_length=1, max_length=20000)
    evidence: EvidenceRequest


class DormancyRunRequest(StrictRequest):
    account_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    jurisdiction: str = Field(default="IN-RBI-DEA", min_length=1, max_length=64)
    balance: float = Field(ge=0)
    last_customer_activity: date
    as_of_date: date


class OutreachResponseRequest(StrictRequest):
    responded_on: date
    channel: Literal["EMAIL", "SMS", "WHATSAPP", "IVR", "APP", "LETTER"]
    request_reactivation: bool = True


class ReactivationRequest(StrictRequest):
    kyc_confirmed: bool
    kyc_route: Literal["V_CIP", "BRANCH_KYC", "DIGITAL_KYC"] = "V_CIP"


class ReclaimRequest(StrictRequest):
    claim_id: str = Field(min_length=1, max_length=64)


class ApprovalDecisionRequest(StrictRequest):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(default="", max_length=1000)


class AutomationPauseRequest(StrictRequest):
    paused: bool
    reason: str = Field(min_length=10, max_length=500)


class Runtime:
    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory
        self.tokens: dict[str, AuthenticatedUser] = {}

    def services(self) -> tuple[LocalRepository, AuditLog, DormancyAgent, BankStatementDatabase]:
        repository = LocalRepository(self.data_directory / "state.json")
        audit = AuditLog(self.data_directory / "audit.jsonl")
        policy = PolicyConfig.from_data_directory(self.data_directory)
        dormancy = DormancyAgent(repository, audit, policy, self.data_directory / "dormancy_cases.sqlite3")
        statements = BankStatementDatabase(self.data_directory / "bank_statement_analysis.sqlite3")
        return repository, audit, dormancy, statements


def create_app(data_directory: str | Path | None = None) -> FastAPI:
    data_path = Path(data_directory) if data_directory else Path(os.getenv("BANKING_DATA_DIR", Path.cwd() / "data"))
    runtime = Runtime(data_path)
    security = HTTPBearer(auto_error=False)
    api = FastAPI(
        title="Banking Verification and Dormancy AI API",
        version="2.0.0",
        description="Human-controlled APIs for bank-statement/AA verification and dormant-account lifecycle management.",
    )
    origins = [item.strip() for item in os.getenv("BANKING_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if item.strip() and item.strip() != "*"]
    api.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

    @api.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else f"req_{uuid4().hex}"
        result = await call_next(request)
        result.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/"):
            result.headers["Cache-Control"] = "no-store"
        return result

    @api.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        detail = error.detail if isinstance(error.detail, str) else "Request could not be completed."
        return JSONResponse(status_code=error.status_code, media_type="application/problem+json", content={"title": detail, "status": error.status_code, "detail": detail, "requestId": request.state.request_id})

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        violations = [{"field": ".".join(str(item) for item in issue["loc"] if item not in {"body", "query"}), "message": issue["msg"]} for issue in error.errors()]
        return JSONResponse(status_code=422, media_type="application/problem+json", content={"title": "Request validation failed.", "status": 422, "detail": "One or more fields are invalid.", "violations": violations, "requestId": request.state.request_id})

    def response(request: Request, data: Any, status: int = 200) -> JSONResponse:
        return JSONResponse(status_code=status, content={"data": data, "meta": {"requestId": request.state.request_id}})

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> AuthenticatedUser:
        if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials not in runtime.tokens:
            raise HTTPException(401, "Authentication is required.")
        return runtime.tokens[credentials.credentials]

    def allow(current: AuthenticatedUser, *roles: str) -> None:
        if current.role not in roles:
            raise HTTPException(403, "This role is not allowed to perform the operation.")

    def owned_customer(current: AuthenticatedUser, requested: str) -> str:
        if current.role == "CUSTOMER":
            if requested and requested != current.customer_id:
                raise HTTPException(404, "Customer record was not found.")
            return current.customer_id
        return requested

    @api.get("/api/v1/health", tags=["Platform"])
    def health(request: Request):
        return response(request, {"status": "ok", "scope": ["BANK_STATEMENT_VERIFICATION", "DORMANCY_ESCHEATMENT"]})

    @api.post("/api/v1/auth/login", tags=["Authentication"])
    def login(payload: LoginRequest, request: Request):
        user = authenticate_local_user(data_path, payload.username, payload.password, payload.user_type)
        if user is None:
            raise HTTPException(401, "Invalid username, password, or role.")
        token = secrets.token_urlsafe(32); runtime.tokens[token] = user
        return response(request, {"accessToken": token, "tokenType": "bearer", "user": asdict(user)})

    @api.post("/api/v1/financial-documents", tags=["Bank statements"])
    async def upload_financial_documents(
        request: Request,
        files: list[UploadFile] = File(...),
        document_type: Literal["BANK_STATEMENT", "ITR", "GST"] = Form("BANK_STATEMENT"),
        password: str = Form(""),
        current: AuthenticatedUser = Depends(identity),
    ):
        allow(current, "CUSTOMER", "UNDERWRITER", "ADMIN")
        if len(files) > 24:
            raise HTTPException(422, "A maximum of 24 documents can be processed per request.")
        _, audit, _, database = runtime.services(); results = []
        for item in files:
            content = await item.read()
            suffix = Path(item.filename or "").suffix.lower()
            if suffix not in {".pdf", ".jpg", ".jpeg"}:
                raise HTTPException(422, "Please upload a PDF or JPG financial document.")
            if not content or len(content) > 10 * 1024 * 1024:
                raise HTTPException(422, "Each financial document must be non-empty and no larger than 10 MB.")
            valid = content.startswith(b"%PDF-") if suffix == ".pdf" else content.startswith(b"\xff\xd8\xff")
            if not valid:
                raise HTTPException(422, "Document content does not match its file extension.")
            protected = False; status = "OCR_REVIEW_REQUIRED" if suffix != ".pdf" else "TEXT_EXTRACTION_PENDING"
            if suffix == ".pdf":
                try:
                    reader = PdfReader(item.file if False else __import__("io").BytesIO(content))
                    protected = reader.is_encrypted
                    if protected and (not password or reader.decrypt(password) == 0):
                        raise HTTPException(422, "The PDF is password protected. Supply the correct password before processing.")
                    extracted = "".join(page.extract_text() or "" for page in reader.pages)
                    status = "EXTRACTED_TEXT_REVIEW_REQUIRED" if extracted.strip() else "OCR_REVIEW_REQUIRED"
                except HTTPException:
                    raise
                except Exception as error:
                    raise HTTPException(422, "The PDF could not be validated or read.") from error
            document_id = f"DOC-{uuid4().hex[:16].upper()}"
            owner = current.customer_id if current.role == "CUSTOMER" else current.username
            database.save_document(document_id, owner, document_type, item.content_type or "application/octet-stream", content, status, protected)
            target = data_path / "uploads" / owner; target.mkdir(parents=True, exist_ok=True)
            (target / f"{document_id}{suffix}").write_bytes(content)
            audit.write(current.username, "financial_document.uploaded", document_id, status, {"document_type": document_type, "size": len(content), "password_protected": protected})
            results.append({"documentId": document_id, "documentType": document_type, "status": status, "message": "Bank document has been uploaded successfully."})
        return response(request, results, 201)

    @api.post("/api/v1/bank-statement-analyses", tags=["Bank statements"])
    def analyze_statement(payload: AnalyzeStatementRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER", "UNDERWRITER", "ADMIN")
        if payload.header.period_start > payload.header.period_end:
            raise HTTPException(422, "Statement period start cannot be after period end.")
        customer_id = owned_customer(current, payload.customer_id)
        if not customer_id:
            raise HTTPException(422, "customer_id is required for staff-submitted analysis.")
        header = StatementHeader(**{**payload.header.model_dump(), "period_start": payload.header.period_start.isoformat(), "period_end": payload.header.period_end.isoformat()})
        transactions = [Transaction(**{**item.model_dump(), "transaction_date": item.transaction_date.isoformat()}) for item in payload.transactions]
        evidence = VerificationEvidence(**{**payload.evidence.model_dump(), "consented_at": payload.evidence.consented_at.astimezone(timezone.utc).isoformat()})
        try:
            analysis = BankStatementAnalysisAgent().analyze(payload.analysis_id or f"BSA-{uuid4().hex[:16].upper()}", header, transactions, evidence)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        _, audit, _, database = runtime.services(); database.save_analysis(customer_id, analysis)
        audit.write(current.username, "bank_statement.analysis_completed", analysis.analysis_id, "REVIEW_REQUIRED", {"risk_level": analysis.risk_level, "risk_score": analysis.risk_score, "source": evidence.source})
        return response(request, asdict(analysis), 201)

    @api.get("/api/v1/bank-statement-analyses/{analysis_id}", tags=["Bank statements"])
    def get_analysis(analysis_id: str, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "UNDERWRITER", "ADMIN")
        _, _, _, database = runtime.services()
        try:
            result = database.get_analysis(analysis_id)
        except KeyError as error:
            raise HTTPException(404, "Analysis was not found.") from error
        return response(request, result)

    @api.get("/api/v1/accounts", tags=["Dormant accounts"])
    def accounts(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER", "COMPLIANCE", "ADMIN")
        repository, _, _, _ = runtime.services(); items = repository.list_accounts()
        if current.role == "CUSTOMER": items = [item for item in items if item.customer_id == current.customer_id]
        return response(request, [asdict(item) for item in items])

    @api.post("/api/v1/dormancy/cycles", tags=["Dormant accounts"])
    def dormancy_cycle(payload: DormancyRunRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN")
        repository, _, agent, _ = runtime.services()
        if payload.jurisdiction not in agent.policy.dormancy_days_by_jurisdiction: raise HTTPException(422, "Jurisdiction is not configured in the active rule pack.")
        if payload.last_customer_activity > payload.as_of_date: raise HTTPException(422, "last_customer_activity cannot be after as_of_date.")
        repository.save_account(Account(payload.account_id, payload.customer_id, payload.jurisdiction, payload.balance, payload.last_customer_activity.isoformat()))
        updated = next(item for item in agent.run(payload.as_of_date) if item.account_id == payload.account_id)
        return response(request, asdict(updated))

    @api.post("/api/v1/accounts/{account_id}/outreach-responses", tags=["Dormant accounts"])
    def outreach_response(account_id: str, payload: OutreachResponseRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER"); repository, _, agent, _ = runtime.services()
        try: account = repository.get_account(account_id)
        except KeyError as error: raise HTTPException(404, "Account was not found.") from error
        if account.customer_id != current.customer_id: raise HTTPException(404, "Account was not found.")
        try: updated = agent.record_customer_response(account_id, payload.responded_on, payload.channel, payload.request_reactivation)
        except ValueError as error: raise HTTPException(409, str(error)) from error
        return response(request, asdict(updated))

    @api.post("/api/v1/accounts/{account_id}/reactivation-requests", tags=["Dormant accounts"])
    def reactivation(account_id: str, payload: ReactivationRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER"); repository, audit, _, _ = runtime.services()
        try: account = repository.get_account(account_id)
        except KeyError as error: raise HTTPException(404, "Account was not found.") from error
        if account.customer_id != current.customer_id: raise HTTPException(404, "Account was not found.")
        if not payload.kyc_confirmed: raise HTTPException(422, "Current KYC confirmation is required.")
        if account.status not in {DormancyStatus.OUTREACH.value, DormancyStatus.DORMANT.value, DormancyStatus.TRANSFER_PENDING.value}: raise HTTPException(409, "Only an account in the dormancy workflow can be reactivated.")
        approval = repository.create_approval(Approval(f"APR-{len(repository.list_approvals()) + 1:04d}", "ACCOUNT_REACTIVATION", account_id, "compliance.officer", {"kyc_route": payload.kyc_route, "external_kyc_verification": "REQUIRED"}, requires_checker=True))
        account.kyc_route = payload.kyc_route; account.reactivation_requested_on = date.today().isoformat(); repository.save_account(account)
        audit.write(current.username, "dormancy.reactivation_requested", account_id, "PENDING", {"approval_id": approval.approval_id})
        return response(request, asdict(approval), 201)

    @api.post("/api/v1/accounts/{account_id}/reclaims", tags=["Dormant accounts"])
    def reclaim(account_id: str, payload: ReclaimRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "CUSTOMER"); repository, _, agent, _ = runtime.services()
        try: account = repository.get_account(account_id)
        except KeyError as error: raise HTTPException(404, "Account was not found.") from error
        if account.customer_id != current.customer_id: raise HTTPException(404, "Account was not found.")
        try: updated = agent.request_claim(account_id, payload.claim_id, True)
        except ValueError as error: raise HTTPException(409, str(error)) from error
        approval = next(item for item in repository.list_approvals() if item.entity_id == account_id and item.kind == "CUSTOMER_RECLAIM" and item.status == "PENDING")
        approval.package["external_kyc_entitlement_verification"] = "REQUIRED_BEFORE_PAYOUT"; repository.save_approval(approval)
        return response(request, {"account": asdict(updated), "approval": asdict(approval)}, 201)

    @api.get("/api/v1/approvals", tags=["Approvals"])
    def approvals(request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN"); repository, _, _, _ = runtime.services()
        return response(request, [asdict(item) for item in repository.list_approvals() if item.required_role in {"compliance.officer", "claims.officer"}])

    @api.post("/api/v1/approvals/{approval_id}/decision", tags=["Approvals"])
    def decide(approval_id: str, payload: ApprovalDecisionRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN"); repository, audit, agent, _ = runtime.services()
        try: approval = repository.get_approval(approval_id)
        except KeyError as error: raise HTTPException(404, "Approval was not found.") from error
        if approval.required_role not in {"compliance.officer", "claims.officer"}: raise HTTPException(403, "Approval is outside the retained workflow scope.")
        if approval.status not in {"PENDING", "MAKER_APPROVED"}: raise HTTPException(409, "Approval has already been decided.")
        if payload.decision == "REJECTED" and not payload.note.strip(): raise HTTPException(422, "A rejection note is required.")
        if approval.requires_checker and approval.status == "PENDING" and payload.decision == "APPROVED":
            approval.status = "MAKER_APPROVED"; approval.maker_by = current.username; approval.maker_note = payload.note; repository.save_approval(approval)
            audit.write(current.username, "approval.maker_approved", approval.entity_id, "PENDING_CHECKER", {"approval_id": approval_id})
            return response(request, {"approval": asdict(approval), "updated": None})
        if approval.requires_checker and approval.status == "MAKER_APPROVED":
            if approval.maker_by == current.username: raise HTTPException(403, "Maker and checker must be different authenticated users.")
            approval.checker_by = current.username
        approval.status = payload.decision; approval.decision_by = current.username; approval.decision_note = payload.note; repository.save_approval(approval)
        updated = None
        if approval.kind == "ACCOUNT_REACTIVATION" and payload.decision == "APPROVED":
            account = repository.get_account(approval.entity_id); account.status = DormancyStatus.ACTIVE.value; account.cbs_status = "REACTIVATED_LOCAL_DEMO"; account.last_customer_activity = date.today().isoformat(); repository.save_account(account); updated = asdict(account)
        transfers = agent.execute_approved_transfers() if approval.kind == "UNCLAIMED_TRANSFER" and payload.decision == "APPROVED" else []
        claims = agent.execute_approved_claims() if approval.kind == "CUSTOMER_RECLAIM" and payload.decision == "APPROVED" else []
        audit.write(current.username, "approval.decided", approval.entity_id, payload.decision, {"approval_id": approval_id})
        return response(request, {"approval": asdict(approval), "updated": updated, "transfers": [asdict(item) for item in transfers], "claims": [asdict(item) for item in claims]})

    @api.get("/api/v1/dormancy/deadline-alerts", tags=["Dormant accounts"])
    def alerts(request: Request, as_of_date: date, within_days: int = 90, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN")
        if not 0 <= within_days <= 3650: raise HTTPException(422, "within_days must be between 0 and 3650.")
        _, _, agent, _ = runtime.services(); return response(request, agent.deadline_alerts(as_of_date, within_days))

    @api.post("/api/v1/accounts/{account_id}/automation-pause", tags=["Dormant accounts"])
    def pause(account_id: str, payload: AutomationPauseRequest, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN"); repository, _, agent, _ = runtime.services()
        try: repository.get_account(account_id)
        except KeyError as error: raise HTTPException(404, "Account was not found.") from error
        return response(request, asdict(agent.set_automation_pause(account_id, payload.paused, current.username, payload.reason)))

    @api.get("/api/v1/accounts/{account_id}/regulatory-export", tags=["Dormant accounts"])
    def regulatory_export(account_id: str, request: Request, current: AuthenticatedUser = Depends(identity)):
        allow(current, "COMPLIANCE", "ADMIN"); repository, audit, agent, _ = runtime.services()
        try: repository.get_account(account_id)
        except KeyError as error: raise HTTPException(404, "Account was not found.") from error
        result = agent.regulatory_export(account_id); audit.write(current.username, "regulatory.export_generated", account_id, "SUCCESS", {"schema_version": result["schema_version"], "simulation": True})
        return response(request, result)

    return api


app = create_app()
