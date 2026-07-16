from __future__ import annotations

"""Append-only audit log for workflow events.

This file records every significant workflow action so the demo has a visible
history for loan review, approval decisions, dormancy processing, and automation.
"""

import json
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
        event = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "entity_id": entity_id,
            "outcome": outcome,
            "detail": detail,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
