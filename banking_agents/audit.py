from __future__ import annotations

"""Append-only audit log for workflow events.

This file records every significant workflow action so the demo has a visible
history for loan review, approval decisions, dormancy processing, and automation.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, actor: str, action: str, entity_id: str, outcome: str, detail: dict[str, Any]) -> None:
        # Feature: audit trail for loan, approval, dormancy, and automation events.
        # Database connection: appends event records to data/audit.jsonl.
        previous_hash = self._last_hash()
        event = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "entity_id": entity_id,
            "outcome": outcome,
            "detail": detail,
            "previous_hash": previous_hash,
        }
        event["event_hash"] = hashlib.sha256(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _last_hash(self) -> str:
        """Return the prior event hash for a local tamper-evident chain."""
        if not self.path.exists():
            return "GENESIS"
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return "GENESIS"
        try:
            previous = json.loads(lines[-1])
        except json.JSONDecodeError:
            return "INVALID_PREVIOUS_EVENT"
        return previous.get("event_hash", "LEGACY_UNCHAINED_EVENT")
