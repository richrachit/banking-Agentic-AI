from __future__ import annotations

"""Loan exception and review workflow engine.

This module connects the loan UI, the document verification rules, and the
repository so loan applications can be processed, rejected, approved, or reopened.
"""

from pathlib import Path

from .audit import AuditLog
from .document_verification import DocumentVerificationModel
from .loan_exception_platform import LoanExceptionDatabase, PolicyVarianceSandbox
from .models import Approval, LoanApplication, LoanStatus
from .policy import PolicyConfig
from .repository import LocalRepository


class LoanExceptionAgent:
    def __init__(self, repository: LocalRepository, audit: AuditLog, policy: PolicyConfig, document_model: DocumentVerificationModel | None = None, exception_db_path: str | Path | None = None) -> None:
        self.repository, self.audit, self.policy = repository, audit, policy
        self.document_model = document_model or DocumentVerificationModel()
        self.policy_sandbox = PolicyVarianceSandbox(tolerance_ratio=policy.income_variance_tolerance)
        self.exception_db = LoanExceptionDatabase(exception_db_path or Path.cwd() / "data" / "loan_exception_cases.sqlite3") if exception_db_path is not None or Path.cwd().exists() else None

    def run(self, application_id: str) -> LoanApplication:
        loan = self.repository.get_loan(application_id)
        if loan.status == LoanStatus.READY_FOR_MAIN_JOURNEY.value:
            return loan
        if loan.exception_code == "MISSING_DOCUMENT":
            return self._resolve_missing_document(loan)
        if loan.exception_code == "VERIFY_TRANSIENT_FAILURE":
            return self._retry_verification(loan)
        if loan.exception_code == "INCOME_VARIANCE":
            return self._resolve_income_variance(loan)
        loan.diagnosis = f"Unsupported exception: {loan.exception_code}"
        self.repository.save_loan(loan)
        self.audit.write("loan-agent", "loan.diagnosed", loan.application_id, "MANUAL_REVIEW", {"exception": loan.exception_code})
        return loan

    def apply_approved_deviation(self, application_id: str) -> LoanApplication:
        loan = self.repository.get_loan(application_id)
        approved = [item for item in self.repository.list_approvals() if item.entity_id == application_id and item.kind == "LOAN_DEVIATION" and item.status == "APPROVED"]
        if approved and loan.status == LoanStatus.AWAITING_APPROVAL.value:
            loan.status = LoanStatus.READY_FOR_MAIN_JOURNEY.value
            loan.diagnosis = "Credit deviation approved; returned to main journey."
            self.repository.save_loan(loan)
            self.audit.write("loan-agent", "loan.returned_to_journey", application_id, "SUCCESS", {"approval_id": approved[0].approval_id})
        return loan

    def approve_application(self, application_id: str, reason: str) -> LoanApplication:
        # Feature: direct approve action from the dashboard review queue.
        # Database connection: updates the loan status in data/state.json.
        loan = self.repository.get_loan(application_id)
        if loan.status == LoanStatus.AWAITING_APPROVAL.value or loan.credit_score_decision in {
            "REJECTED_LOW_SCORE",
            "HUMAN_REVIEW",
            "HUMAN_REVIEW_BUREAU_UNAVAILABLE",
            "HUMAN_REVIEW_REJECTED",
            "LOW_SCORE_RECONSIDERATION_REJECTED",
        }:
            raise ValueError("A Loan Operations action cannot bypass the required Credit Manager decision.")
        loan.status = LoanStatus.READY_FOR_MAIN_JOURNEY.value
        loan.diagnosis = f"Application approved by operations: {reason}"
        self.repository.save_loan(loan)
        self.audit.write("loan-agent", "loan.approved", application_id, "APPROVED", {"reason": reason})
        return loan

    def reject_application(self, application_id: str, reason: str) -> LoanApplication:
        # Feature: AI or operations rejection for loans that need rework.
        # Database connection: updates the loan status and audit trail in storage.
        loan = self.repository.get_loan(application_id)
        loan.status = LoanStatus.REJECTED.value
        loan.diagnosis = f"Application rejected: {reason}"
        self.repository.save_loan(loan)
        self.audit.write("loan-agent", "loan.rejected", application_id, "REJECTED", {"reason": reason})
        return loan

    def reopen_application(self, application_id: str, reason: str) -> LoanApplication:
        loan = self.repository.get_loan(application_id)
        loan.status = LoanStatus.AWAITING_CUSTOMER.value
        loan.diagnosis = f"Application reopened for review: {reason}"
        self.repository.save_loan(loan)
        self.audit.write("loan-agent", "loan.reopened", application_id, "AWAITING_CUSTOMER", {"reason": reason})
        return loan

    def _resolve_missing_document(self, loan: LoanApplication) -> LoanApplication:
        # Supports legacy received-document lists and richer per-document verification evidence.
        evidence = {item.upper().strip(): "VALID" for item in loan.documents} | {item.upper().strip(): status for item, status in loan.document_evidence.items()}
        result = self.document_model.verify(loan.loan_product, evidence, loan.requested_documents)
        missing = [*result.missing, *[f"{item} (replace: {evidence[item]})" for item in result.invalid]]
        if missing:
            loan.status = LoanStatus.AWAITING_CUSTOMER.value
            loan.diagnosis = f"Document verification incomplete: {', '.join(missing)}"
            self.audit.write("loan-agent", "customer.document_requested", loan.application_id, "PENDING", {"documents": missing, "loan_product": loan.loan_product})
        else:
            loan.status = LoanStatus.READY_FOR_MAIN_JOURNEY.value
            loan.diagnosis = "All required documents are present and valid."
            self.audit.write("loan-agent", "loan.returned_to_journey", loan.application_id, "SUCCESS", {})
        self.repository.save_loan(loan)
        return loan

    def _retry_verification(self, loan: LoanApplication) -> LoanApplication:
        loan.verification_attempts += 1
        if loan.verification_attempts >= 2:
            loan.status = LoanStatus.READY_FOR_MAIN_JOURNEY.value
            loan.diagnosis = "Verification succeeded on retry."
            outcome = "SUCCESS"
        else:
            loan.status = LoanStatus.AWAITING_CUSTOMER.value
            loan.diagnosis = "Verification still unavailable; customer confirmation requested."
            outcome = "PENDING"
        self.repository.save_loan(loan)
        self.audit.write("loan-agent", "verification.retried", loan.application_id, outcome, {"attempt": loan.verification_attempts})
        return loan

    def _resolve_income_variance(self, loan: LoanApplication) -> LoanApplication:
        decision = self.policy_sandbox.evaluate_variance(loan.declared_income, loan.verified_income)
        if decision.safe_to_auto_adjust:
            loan.status = LoanStatus.READY_FOR_MAIN_JOURNEY.value
            loan.diagnosis = "Income variance is within policy tolerance."
            self.repository.save_loan(loan)
            self.audit.write("loan-agent", "loan.auto_resolved", loan.application_id, "SUCCESS", {"rule": "income_tolerance"})
            self._persist_exception_case(loan, decision)
            return loan
        approval = self.repository.create_approval(Approval(
            approval_id=f"APR-{len(self.repository.list_approvals()) + 1:04d}", kind="LOAN_DEVIATION", entity_id=loan.application_id,
            required_role="credit.manager", package={"declared_income": loan.declared_income, "verified_income": loan.verified_income, "diagnosis": "Income variance exceeds tolerance"},
        ))
        loan.status = LoanStatus.AWAITING_APPROVAL.value
        loan.diagnosis = f"Income variance exceeds policy; routed to {approval.required_role}."
        self.repository.save_loan(loan)
        self.audit.write("loan-agent", "approval.requested", loan.application_id, "PENDING", {"approval_id": approval.approval_id, "kind": approval.kind})
        self._persist_exception_case(loan, decision)
        return loan

    def _persist_exception_case(self, loan: LoanApplication, decision) -> None:
        if self.exception_db is None:
            return
        case_id = self.exception_db.create_case(loan.application_id, loan.exception_code, customer_name=loan.applicant_name or loan.relationship_manager or "Unknown")
        self.exception_db.save_policy_decision(case_id, loan.declared_income, loan.verified_income, decision.action, decision.rationale)
        if loan.documents:
            self.exception_db.save_document(case_id, "loan_documents", "loan_documents", ", ".join(loan.documents), 80, [], {"documents": loan.documents}, False)
