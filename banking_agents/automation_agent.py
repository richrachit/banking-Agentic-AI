from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .audit import AuditLog
from .dormancy_agent import DormancyAgent
from .repository import LocalRepository


@dataclass
class AutomationResult:
    as_of: str
    actions: list[str] = field(default_factory=list)
    pending_human_actions: list[str] = field(default_factory=list)


class OperationsAutomationAgent:
    """Runs the retained dormant lifecycle; money movement remains approval-gated."""

    def __init__(self, repository: LocalRepository, audit: AuditLog, dormancy_agent: DormancyAgent) -> None:
        self.repository, self.audit, self.dormancy_agent = repository, audit, dormancy_agent

    def run_cycle(self, as_of: date) -> AutomationResult:
        result = AutomationResult(as_of.isoformat())
        for account in self.dormancy_agent.run(as_of): result.actions.append(f"Account {account.account_id}: {account.status}")
        for account in self.dormancy_agent.execute_approved_transfers(): result.actions.append(f"Account {account.account_id}: transfer executed")
        for account in self.dormancy_agent.execute_approved_claims(): result.actions.append(f"Account {account.account_id}: claim paid")
        for approval in self.repository.list_approvals():
            if approval.status in {"PENDING", "MAKER_APPROVED"}: result.pending_human_actions.append(f"{approval.required_role}: {approval.approval_id}")
        self.audit.write("operations-orchestrator", "automation.cycle_completed", "DORMANCY", "SUCCESS", {"as_of": result.as_of, "actions": len(result.actions), "pending": len(result.pending_human_actions)})
        return result
