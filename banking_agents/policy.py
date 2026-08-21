from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class PolicyConfig:
    income_variance_tolerance: float = 0.10
    outreach_lead_days: int = 30
    outreach_channels: tuple[str, ...] = ("EMAIL", "SMS", "WHATSAPP", "IVR", "APP", "LETTER")
    # Illustrative only: confirm approved legal/policy periods before production use.
    dormancy_days_by_jurisdiction: dict[str, int] | None = None
    transfer_wait_days_by_jurisdiction: dict[str, int] | None = None
    annual_interest_rate_by_jurisdiction: dict[str, float] | None = None
    deadline_alert_days_by_jurisdiction: dict[str, tuple[int, ...]] | None = None
    filing_types_by_jurisdiction: dict[str, tuple[str, ...]] | None = None

    def __post_init__(self) -> None:
        # Illustrative local values only: classify after two years, then keep a
        # separate clock until the ten-year unclaimed-deposit milestone.
        object.__setattr__(self, "dormancy_days_by_jurisdiction", self.dormancy_days_by_jurisdiction or {"IN-RBI-DEA": 365 * 2})
        object.__setattr__(self, "transfer_wait_days_by_jurisdiction", self.transfer_wait_days_by_jurisdiction or {"IN-RBI-DEA": 365 * 8})
        object.__setattr__(self, "annual_interest_rate_by_jurisdiction", self.annual_interest_rate_by_jurisdiction or {"IN-RBI-DEA": 0.0})
        object.__setattr__(self, "deadline_alert_days_by_jurisdiction", self.deadline_alert_days_by_jurisdiction or {"IN-RBI-DEA": (90, 30, 7, 1)})
        object.__setattr__(self, "filing_types_by_jurisdiction", self.filing_types_by_jurisdiction or {"IN-RBI-DEA": ("DEA_REMITTANCE", "UDGAM_PUBLICATION")})

    @classmethod
    def from_rule_pack_file(cls, path: str | Path) -> "PolicyConfig":
        """Load jurisdiction lifecycle settings without changing application code."""
        source = Path(path)
        if not source.exists():
            return cls()
        payload = json.loads(source.read_text(encoding="utf-8"))
        packs = payload.get("jurisdictions", {})
        if not isinstance(packs, dict) or not packs:
            raise ValueError("At least one jurisdiction rule-pack is required.")
        dormancy: dict[str, int] = {}
        transfer: dict[str, int] = {}
        interest: dict[str, float] = {}
        alerts: dict[str, tuple[int, ...]] = {}
        filings: dict[str, tuple[str, ...]] = {}
        for jurisdiction, values in packs.items():
            if not isinstance(values, dict):
                raise ValueError(f"Rule-pack {jurisdiction} must be an object.")
            dormancy[jurisdiction] = int(values["dormancy_days"])
            transfer[jurisdiction] = int(values["transfer_wait_days"])
            interest[jurisdiction] = float(values.get("annual_interest_rate", 0.0))
            alerts[jurisdiction] = tuple(int(item) for item in values.get("deadline_alert_days", [90, 30, 7, 1]))
            filings[jurisdiction] = tuple(str(item) for item in values.get("filing_types", []))
            if dormancy[jurisdiction] <= 0 or transfer[jurisdiction] < 0 or not 0 <= interest[jurisdiction] <= 1:
                raise ValueError(f"Rule-pack {jurisdiction} contains invalid thresholds or interest rate.")
        channels = tuple(str(item).upper() for item in payload.get("outreach_channels", cls().outreach_channels))
        return cls(
            outreach_lead_days=int(payload.get("outreach_lead_days", 30)),
            outreach_channels=channels,
            dormancy_days_by_jurisdiction=dormancy,
            transfer_wait_days_by_jurisdiction=transfer,
            annual_interest_rate_by_jurisdiction=interest,
            deadline_alert_days_by_jurisdiction=alerts,
            filing_types_by_jurisdiction=filings,
        )

    @classmethod
    def from_data_directory(cls, directory: str | Path) -> "PolicyConfig":
        return cls.from_rule_pack_file(Path(directory) / "jurisdiction_rule_packs.json")

    def income_within_tolerance(self, declared: float, verified: float) -> bool:
        if declared <= 0:
            return False
        return abs(declared - verified) / declared <= self.income_variance_tolerance
