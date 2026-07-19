"""Explainable process-progress view for UI/API consumers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressStage:
    name: str
    owner: str
    ai_active: bool
    completed: bool


LOAN_STAGES = (
    ("Application submitted", "Customer", False),
    ("Consent and credit-bureau assessment", "Credit Bureau Agent", True),
    ("Data and document validation", "AI Agent", True),
    ("Fraud and credit assessment", "AI Agent", True),
    ("Policy decision", "AI Agent", True),
    ("Manual exception review", "Loan Operations / Credit Manager", False),
    ("eSign and acceptance", "Customer", False),
    ("Disbursement", "Operations", False),
)

def loan_progress(status: str, exception_code: str = "") -> list[ProgressStage]:
    """Returns a truthful, user-facing progression; AI starts at validation."""
    manual = status in {"AWAITING_APPROVAL", "AWAITING_CUSTOMER", "HELD"}
    complete = status == "READY_FOR_MAIN_JOURNEY"
    rejected = status == "REJECTED"
    stages: list[ProgressStage] = []
    for index, (name, owner, ai_active) in enumerate(LOAN_STAGES):
        done = index == 0 or (rejected and index <= 1) or (index <= 4 and (manual or complete)) or (index == 5 and complete)
        stages.append(ProgressStage(name, owner, ai_active, done))
    return stages
