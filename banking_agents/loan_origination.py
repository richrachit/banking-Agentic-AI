from __future__ import annotations

"""Shared customer-loan submission service for browser and JSON API clients."""

from .credit_bureau_agent import CreditBureauDecisionAgent, CreditScoreUnavailable
from .loan_agent import LoanExceptionAgent
from .models import LoanApplication, LoanStatus
from .repository import LocalRepository


class LoanOriginationService:
    def __init__(
        self,
        repository: LocalRepository,
        loan_agent: LoanExceptionAgent,
        credit_bureau_agent: CreditBureauDecisionAgent,
    ) -> None:
        self.repository = repository
        self.loan_agent = loan_agent
        self.credit_bureau_agent = credit_bureau_agent

    def submit(
        self,
        loan: LoanApplication,
        pan_for_bureau_lookup: str,
        credit_bureau_consent: bool,
        consent_version: str = CreditBureauDecisionAgent.supported_consent_version,
    ) -> LoanApplication:
        """Persists, fetches the bureau signal, then enters the existing workflow."""
        self.repository.save_loan(loan)
        try:
            assessed = self.credit_bureau_agent.assess(
                loan.application_id,
                pan_for_bureau_lookup,
                credit_bureau_consent,
                consent_version,
            )
        except CreditScoreUnavailable:
            assessed = self.credit_bureau_agent.route_unavailable(loan.application_id)
        if assessed.status == LoanStatus.HELD.value:
            return self.loan_agent.run(assessed.application_id)
        return assessed

    def continue_after_credit_review(
        self,
        application_id: str,
        approved: bool,
        reason: str,
    ) -> LoanApplication:
        """Resume document checks only after an authorised credit decision."""
        loan = self.repository.get_loan(application_id)
        if approved:
            loan.status = LoanStatus.HELD.value
            loan.credit_score_decision = "HUMAN_REVIEW_APPROVED"
            loan.diagnosis = "Credit Manager approved continuation to the loan checks."
            self.repository.save_loan(loan)
            return self.loan_agent.run(application_id)
        loan.credit_score_decision = "HUMAN_REVIEW_REJECTED"
        self.repository.save_loan(loan)
        return self.loan_agent.reject_application(application_id, reason)
