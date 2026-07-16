"""Autonomous supervisor that delegates to constrained banking workflow agents.

Feature connection: this orchestrates the loan and dormancy workflows from the
UI and persists the resulting actions through the repository and audit log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .audit import AuditLog
from .dormancy_agent import DormancyAgent
from .loan_agent import LoanExceptionAgent
from .models import LoanStatus
from .repository import LocalRepository


@dataclass
class AutomationResult:
    as_of: str
    actions: list[str] = field(default_factory=list)
    pending_human_actions: list[str] = field(default_factory=list)


class OperationsAutomationAgent:
    """Runs a safe agent cycle; policy deviations and money movement remain approval-gated."""

    def __init__(self, repository: LocalRepository, audit: AuditLog, loan_agent: LoanExceptionAgent, dormancy_agent: DormancyAgent) -> None:
        self.repository, self.audit = repository, audit
        self.loan_agent, self.dormancy_agent = loan_agent, dormancy_agent

    def run_cycle(self, as_of: date) -> AutomationResult:
        result = AutomationResult(as_of=as_of.isoformat())
        for loan in self.repository.list_loans():
            if loan.status == LoanStatus.HELD.value:
                updated = self.loan_agent.run(loan.application_id)
                result.actions.append(f"Loan {updated.application_id}: {updated.status}")
                if updated.status == LoanStatus.AWAITING_APPROVAL.value:
                    result.pending_human_actions.append(f"Credit decision required for loan {updated.application_id}")
            elif loan.status == LoanStatus.AWAITING_APPROVAL.value:
                updated = self.loan_agent.apply_approved_deviation(loan.application_id)
                if updated.status == LoanStatus.AWAITING_APPROVAL.value:
                    result.pending_human_actions.append(f"Credit decision required for loan {updated.application_id}")
                else:
                    result.actions.append(f"Loan {updated.application_id}: returned to main journey")
        for account in self.dormancy_agent.run(as_of):
            result.actions.append(f"Account {account.account_id}: {account.status}")
        for account in self.dormancy_agent.execute_approved_transfers():
            result.actions.append(f"Account {account.account_id}: transfer executed")
        for account in self.dormancy_agent.execute_approved_claims():
            result.actions.append(f"Account {account.account_id}: customer claim paid")
        for approval in self.repository.list_approvals():
            if approval.status == "PENDING":
                result.pending_human_actions.append(f"{approval.required_role} approval required: {approval.approval_id}")
        self.audit.write("operations-automation-agent", "automation.cycle_completed", "OPERATIONS", "SUCCESS", {"as_of": result.as_of, "action_count": len(result.actions), "pending_count": len(result.pending_human_actions)})
        return result
