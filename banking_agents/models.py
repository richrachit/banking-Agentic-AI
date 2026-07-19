from __future__ import annotations

"""Core domain models for loans, accounts, approvals, and workflow state.

These models define the business objects that are passed between the web app,
the agents, and the repository persistence layer.
"""

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class LoanStatus(str, Enum):
    HELD = "HELD"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY_FOR_MAIN_JOURNEY = "READY_FOR_MAIN_JOURNEY"
    REJECTED = "REJECTED"
    REOPENED = "REOPENED"


class DormancyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OUTREACH = "OUTREACH"
    DORMANT = "DORMANT"
    TRANSFER_PENDING = "TRANSFER_PENDING"
    TRANSFERRED = "TRANSFERRED"
    CLAIM_PENDING = "CLAIM_PENDING"
    CLAIM_PAID = "CLAIM_PAID"


@dataclass
class LoanApplication:
    application_id: str
    exception_code: str
    loan_product: str = "PERSONAL"
    status: str = LoanStatus.HELD.value
    requested_documents: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    document_evidence: dict[str, str] = field(default_factory=dict)
    verification_attempts: int = 0
    declared_income: float = 0.0
    verified_income: float = 0.0
    relationship_manager: str = ""
    diagnosis: str = ""
    correlation_id: str = ""
    applicant_name: str = ""
    date_of_birth: str = ""
    email: str = ""
    phone: str = ""
    residential_address: str = ""
    employment_type: str = ""
    employer_name: str = ""
    monthly_income: float = 0.0
    requested_amount: float = 0.0
    tenure_months: int = 0
    loan_purpose: str = ""
    submitted_by: str = ""
    credit_score: int | None = None
    credit_score_band: str = "NOT_CHECKED"
    credit_score_provider: str = ""
    credit_score_reference: str = ""
    credit_score_checked_at: str = ""
    credit_score_decision: str = "NOT_CHECKED"


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


def to_record(value: Any) -> dict[str, Any]:
    return asdict(value)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)
