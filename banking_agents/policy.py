from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyConfig:
    income_variance_tolerance: float = 0.10
    outreach_lead_days: int = 30
    # Illustrative only: confirm approved legal/policy periods before production use.
    dormancy_days_by_jurisdiction: dict[str, int] | None = None
    transfer_wait_days_by_jurisdiction: dict[str, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dormancy_days_by_jurisdiction", self.dormancy_days_by_jurisdiction or {"IN-RBI-DEA": 3650})
        object.__setattr__(self, "transfer_wait_days_by_jurisdiction", self.transfer_wait_days_by_jurisdiction or {"IN-RBI-DEA": 0})

    def income_within_tolerance(self, declared: float, verified: float) -> bool:
        if declared <= 0:
            return False
        return abs(declared - verified) / declared <= self.income_variance_tolerance
