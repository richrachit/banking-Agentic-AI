from __future__ import annotations

"""Local persistence layer for the banking workflow demo.

This module is the main data access boundary for the application. It writes
and reads workflow state from data/state.json and is therefore the primary
connection point between the UI/agents and the local database-like storage.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Account, Approval, LoanApplication, to_record


class LocalRepository:
    """Replace this adapter with LOS, core banking, CRM, and payment clients in production."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.exists():
            self._write({"loans": {}, "accounts": {}, "approvals": {}})

    def _read(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def get_loan(self, application_id: str) -> LoanApplication:
        return LoanApplication(**self._read()["loans"][application_id])

    def generate_application_id(self) -> str:
        """Creates the next local-database application ID: LN-YYYYMMDD-####."""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"LN-{today}-"
        existing = [key for key in self._read()["loans"] if key.startswith(prefix)]
        sequence = max((int(key.rsplit("-", 1)[1]) for key in existing if key.rsplit("-", 1)[1].isdigit()), default=0) + 1
        return f"{prefix}{sequence:04d}"

    def list_loans(self) -> list[LoanApplication]:
        return [LoanApplication(**record) for record in self._read()["loans"].values()]

    def save_loan(self, loan: LoanApplication) -> None:
        # Feature: loan submission and loan review updates are persisted here.
        # Database connection: writes the loan record into data/state.json.
        state = self._read(); state["loans"][loan.application_id] = to_record(loan); self._write(state)

    def get_account(self, account_id: str) -> Account:
        return Account(**self._read()["accounts"][account_id])

    def list_accounts(self) -> list[Account]:
        return [Account(**record) for record in self._read()["accounts"].values()]

    def save_account(self, account: Account) -> None:
        state = self._read(); state["accounts"][account.account_id] = to_record(account); self._write(state)

    def create_approval(self, approval: Approval) -> Approval:
        # Feature: approval routing for loan deviations and transfer/claim actions.
        # Database connection: stores approval records in data/state.json.
        state = self._read()
        for record in state["approvals"].values():
            if record["kind"] == approval.kind and record["entity_id"] == approval.entity_id and record["status"] == "PENDING":
                return Approval(**record)
        state["approvals"][approval.approval_id] = to_record(approval); self._write(state)
        return approval

    def get_approval(self, approval_id: str) -> Approval:
        return Approval(**self._read()["approvals"][approval_id])

    def list_approvals(self) -> list[Approval]:
        return [Approval(**record) for record in self._read()["approvals"].values()]

    def save_approval(self, approval: Approval) -> None:
        state = self._read(); state["approvals"][approval.approval_id] = to_record(approval); self._write(state)

    def seed(self, loans: list[LoanApplication], accounts: list[Account]) -> None:
        self._write({"loans": {item.application_id: to_record(item) for item in loans}, "accounts": {item.account_id: to_record(item) for item in accounts}, "approvals": {}})
