from __future__ import annotations

"""Shared customer-loan submission service for browser and JSON API clients."""

from .credit_bureau_agent import CreditBureauDecisionAgent
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
    ) -> LoanApplication:
        """Persists, fetches the bureau signal, then enters the existing workflow."""
        self.repository.save_loan(loan)
        assessed = self.credit_bureau_agent.assess(
            loan.application_id,
            pan_for_bureau_lookup,
            credit_bureau_consent,
        )
        if assessed.status == LoanStatus.HELD.value:
            return self.loan_agent.run(assessed.application_id)
        return assessed
