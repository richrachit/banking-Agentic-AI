from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, actor: str, action: str, entity_id: str, outcome: str, detail: dict[str, Any]) -> None:
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
