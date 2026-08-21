from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Account, Approval, to_record


class LocalRepository:
    """Local dormant-account state adapter; production replaces it with CBS/workflow repositories."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path; self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not state_path.exists(): self._write({"accounts": {}, "approvals": {}})

    def _read(self) -> dict[str, Any]:
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"accounts": state.get("accounts", {}), "approvals": state.get("approvals", {})}

    def _write(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def get_account(self, account_id: str) -> Account:
        return Account(**self._read()["accounts"][account_id])

    def list_accounts(self) -> list[Account]:
        return [Account(**record) for record in self._read()["accounts"].values()]

    def save_account(self, account: Account) -> None:
        state = self._read(); state["accounts"][account.account_id] = to_record(account); self._write(state)

    def create_approval(self, approval: Approval) -> Approval:
        state = self._read()
        for record in state["approvals"].values():
            if record["kind"] == approval.kind and record["entity_id"] == approval.entity_id and record["status"] in {"PENDING", "MAKER_APPROVED"}:
                return Approval(**record)
        state["approvals"][approval.approval_id] = to_record(approval); self._write(state); return approval

    def get_approval(self, approval_id: str) -> Approval:
        return Approval(**self._read()["approvals"][approval_id])

    def list_approvals(self) -> list[Approval]:
        return [Approval(**record) for record in self._read()["approvals"].values()]

    def save_approval(self, approval: Approval) -> None:
        state = self._read(); state["approvals"][approval.approval_id] = to_record(approval); self._write(state)

    def seed(self, accounts: list[Account]) -> None:
        self._write({"accounts": {item.account_id: to_record(item) for item in accounts}, "approvals": {}})
