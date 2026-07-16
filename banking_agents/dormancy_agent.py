from __future__ import annotations

"""Dormancy and escheatment workflow engine.

This module connects account lifecycle processing, approval creation, and the
persisted case database for dormant-account reviews.
"""

from datetime import date, timedelta
from pathlib import Path

from .audit import AuditLog
from .dormancy_escheatment_platform import DormancyCaseDatabase, DormancyIncentiveCalculator
from .models import Account, Approval, DormancyStatus, parse_date
from .policy import PolicyConfig
from .repository import LocalRepository


class DormancyAgent:
    def __init__(self, repository: LocalRepository, audit: AuditLog, policy: PolicyConfig, dormancy_db_path: str | Path | None = None) -> None:
        self.repository, self.audit, self.policy = repository, audit, policy
        self.incentive_calculator = DormancyIncentiveCalculator()
        self.dormancy_db = DormancyCaseDatabase(dormancy_db_path or Path.cwd() / "data" / "dormancy_cases.sqlite3") if dormancy_db_path is not None or Path.cwd().exists() else None

    def run(self, as_of: date) -> list[Account]:
        processed: list[Account] = []
        for account in self.repository.list_accounts():
            processed.append(self._process(account, as_of))
        return processed

    def _process(self, account: Account, as_of: date) -> Account:
        dormancy_days = self.policy.dormancy_days_by_jurisdiction[account.jurisdiction]
        inactive_days = (as_of - parse_date(account.last_customer_activity)).days
        if account.status == DormancyStatus.ACTIVE.value and inactive_days >= dormancy_days - self.policy.outreach_lead_days:
            account.status, account.outreach_sent = DormancyStatus.OUTREACH.value, True
            self.audit.write("dormancy-agent", "customer.reengagement_started", account.account_id, "PENDING", {"channels": ["SMS", "EMAIL", "RM_CALL"]})
        if account.status in (DormancyStatus.ACTIVE.value, DormancyStatus.OUTREACH.value) and inactive_days >= dormancy_days:
            account.status = DormancyStatus.DORMANT.value
            account.dormant_on = as_of.isoformat()
            account.transfer_due_on = (as_of + timedelta(days=self.policy.transfer_wait_days_by_jurisdiction[account.jurisdiction])).isoformat()
            self.audit.write("dormancy-agent", "account.classified_dormant", account.account_id, "SUCCESS", {"transfer_due_on": account.transfer_due_on})
        if account.status == DormancyStatus.DORMANT.value and as_of >= parse_date(account.transfer_due_on or as_of.isoformat()):
            approval = self.repository.create_approval(Approval(
                approval_id=f"APR-{len(self.repository.list_approvals()) + 1:04d}", kind="UNCLAIMED_TRANSFER", entity_id=account.account_id,
                required_role="compliance.officer", package={"jurisdiction": account.jurisdiction, "balance": account.balance, "due_on": account.transfer_due_on},
            ))
            account.status = DormancyStatus.TRANSFER_PENDING.value
            self.audit.write("dormancy-agent", "transfer.approval_requested", account.account_id, "PENDING", {"approval_id": approval.approval_id})
        self.repository.save_account(account)
        self._persist_case(account, as_of, inactive_days)
        return account

    def _persist_case(self, account: Account, as_of: date, inactive_days: int) -> None:
        if self.dormancy_db is None:
            return
        case_id = self.dormancy_db.create_case(account.account_id, account.customer_id, account.jurisdiction, account.balance, as_of, inactive_days)
        self.dormancy_db.record_event(case_id, "ACCOUNT_PROCESSED", f"Status: {account.status}")
        if account.status in {DormancyStatus.OUTREACH.value, DormancyStatus.DORMANT.value, DormancyStatus.TRANSFER_PENDING.value}:
            self.dormancy_db.record_outreach(case_id, "SMS", "SENT", "Outreach queued")
        if account.status in {DormancyStatus.DORMANT.value, DormancyStatus.TRANSFER_PENDING.value, DormancyStatus.TRANSFERRED.value}:
            incentive = self.incentive_calculator.calculate_incentive(account.balance, inactive_days)
            self.dormancy_db.record_trace(case_id, "RBI_RULE_ENGINE", "INCENTIVE_TIER", incentive.rationale, incentive.tier)
            self.dormancy_db.record_filing(case_id, "DEA_REPORT", "PENDING", f"Potential payout: {incentive.amount:.2f}")

    def execute_approved_transfers(self) -> list[Account]:
        updated: list[Account] = []
        for approval in self.repository.list_approvals():
            if approval.kind != "UNCLAIMED_TRANSFER" or approval.status != "APPROVED":
                continue
            account = self.repository.get_account(approval.entity_id)
            if account.status != DormancyStatus.TRANSFER_PENDING.value:
                continue
            account.transferred_amount, account.balance = account.balance, 0.0
            account.status = DormancyStatus.TRANSFERRED.value
            self.repository.save_account(account)
            self.audit.write("dormancy-agent", "dea.transfer_executed", account.account_id, "SUCCESS", {"amount": account.transferred_amount, "approval_id": approval.approval_id})
            updated.append(account)
        return updated

    def request_claim(self, account_id: str, claim_id: str, identity_validated: bool) -> Account:
        """Queues a reclaim only after an external identity/entitlement adapter validates it."""
        account = self.repository.get_account(account_id)
        if account.status != DormancyStatus.TRANSFERRED.value:
            raise ValueError("Claims are allowed only after a transfer has been recorded.")
        if not identity_validated:
            raise ValueError("Identity and entitlement validation is required before a claim can be submitted.")
        approval = self.repository.create_approval(Approval(
            approval_id=f"APR-{len(self.repository.list_approvals()) + 1:04d}", kind="CUSTOMER_RECLAIM", entity_id=account.account_id,
            required_role="claims.officer", package={"claim_id": claim_id, "amount": account.transferred_amount},
        ))
        account.status = DormancyStatus.CLAIM_PENDING.value
        self.repository.save_account(account)
        self.audit.write("dormancy-agent", "customer.claim_submitted", account.account_id, "PENDING", {"approval_id": approval.approval_id, "claim_id": claim_id})
        return account

    def execute_approved_claims(self) -> list[Account]:
        updated: list[Account] = []
        for approval in self.repository.list_approvals():
            if approval.kind != "CUSTOMER_RECLAIM" or approval.status != "APPROVED":
                continue
            account = self.repository.get_account(approval.entity_id)
            if account.status != DormancyStatus.CLAIM_PENDING.value:
                continue
            account.status = DormancyStatus.CLAIM_PAID.value
            self.repository.save_account(account)
            self.audit.write("dormancy-agent", "customer.claim_paid", account.account_id, "SUCCESS", {"amount": account.transferred_amount, "approval_id": approval.approval_id})
            updated.append(account)
        return updated
