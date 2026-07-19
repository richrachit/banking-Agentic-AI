from __future__ import annotations

"""Persisted, fail-closed feature controls for local AI-agent components."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .local_models import MODEL_COMPONENTS


CHATBOT_COMPONENT = {
    "model_key": "banking_support_chatbot",
    "display_name": "Banking Support Chatbot",
    "component_type": "TRAINED_INTENT_RETRIEVAL",
    "training_supported": True,
    "risk_tier": "HIGH",
    "authority_boundary": (
        "Answers role-scoped workflow questions only. It cannot execute banking actions, make decisions, "
        "or retain customer chat text for training."
    ),
}


class AgentSettingsStore:
    """Stores whether each registered component is available in this local runtime.

    A disabled workflow agent must make its dependent route unavailable. This
    prevents a feature toggle from silently bypassing the control it names.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"agents": {}, "updated_at": self._now()})

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        value.setdefault("agents", {})
        return value

    def _write(self, value: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _catalog() -> dict[str, dict[str, Any]]:
        catalog = {
            component.model_key: {
                "model_key": component.model_key,
                "display_name": component.display_name,
                "component_type": component.component_type,
                "training_supported": component.training_supported,
                "risk_tier": component.risk_tier,
                "authority_boundary": component.authority_boundary,
            }
            for component in MODEL_COMPONENTS
        }
        catalog[CHATBOT_COMPONENT["model_key"]] = CHATBOT_COMPONENT.copy()
        return catalog

    def is_enabled(self, model_key: str) -> bool:
        if model_key not in self._catalog():
            raise KeyError(f"Unknown AI agent: {model_key}")
        value = self._read()["agents"].get(model_key, {})
        return bool(value.get("enabled", True))

    def set_enabled(self, model_key: str, enabled: bool, actor: str) -> dict[str, Any]:
        if model_key not in self._catalog():
            raise KeyError(f"Unknown AI agent: {model_key}")
        state = self._read()
        state["agents"][model_key] = {
            "enabled": bool(enabled),
            "changed_by": actor,
            "changed_at": self._now(),
        }
        state["updated_at"] = self._now()
        self._write(state)
        return next(item for item in self.list_settings() if item["model_key"] == model_key)

    def list_settings(self) -> list[dict[str, Any]]:
        saved = self._read()["agents"]
        items = []
        for model_key, component in self._catalog().items():
            configured = saved.get(model_key, {})
            items.append(
                {
                    **component,
                    "enabled": bool(configured.get("enabled", True)),
                    "changed_by": configured.get("changed_by"),
                    "changed_at": configured.get("changed_at"),
                    "fail_closed_when_disabled": True,
                }
            )
        return sorted(items, key=lambda item: item["display_name"])
