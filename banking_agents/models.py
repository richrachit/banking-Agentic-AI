from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class DormancyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OUTREACH = "OUTREACH"
    DORMANT = "DORMANT"
    TRANSFER_PENDING = "TRANSFER_PENDING"
    TRANSFERRED = "TRANSFERRED"
    CLAIM_PENDING = "CLAIM_PENDING"
    CLAIM_PAID = "CLAIM_PAID"


@dataclass
class Account:
    account_id: str
    customer_id: str
    jurisdiction: str
    balance: float
    last_customer_activity: str
    status: str = DormancyStatus.ACTIVE.value
    outreach_sent: bool = False
    dormant_on: str | None = None
    transfer_due_on: str | None = None
    transferred_amount: float = 0.0
    outreach_started_on: str | None = None
    outreach_channels: list[str] = field(default_factory=list)
    customer_responded_on: str | None = None
    response_channel: str | None = None
    kyc_route: str | None = None
    reactivation_requested_on: str | None = None
    statutory_clock_started_on: str | None = None
    transfer_package_prepared_on: str | None = None
    transfer_principal: float = 0.0
    transfer_interest: float = 0.0
    gl_reconciliation_status: str = "NOT_STARTED"
    cbs_status: str = "NOT_STARTED"
    ekuber_status: str = "NOT_STARTED"
    udgam_status: str = "NOT_STARTED"
    regulator_reference: str | None = None
    claim_id: str | None = None
    claim_verified_on: str | None = None
    payout_status: str = "NOT_STARTED"
    automation_paused: bool = False
    pause_reason: str | None = None
    paused_by: str | None = None
    paused_on: str | None = None


@dataclass
class Approval:
    approval_id: str
    kind: str
    entity_id: str
    required_role: str
    package: dict[str, Any]
    status: str = "PENDING"
    decision_by: str | None = None
    decision_note: str | None = None
    requires_checker: bool = False
    maker_by: str | None = None
    maker_note: str | None = None
    checker_by: str | None = None


def to_record(value: Any) -> dict[str, Any]:
    return asdict(value)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)
