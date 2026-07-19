from __future__ import annotations

"""Consent-based credit-bureau lookup and policy-controlled loan routing.

The local provider is a development fixture store, not TransUnion CIBIL. A real
deployment must replace it with the bank's authorised member/API integration.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
from typing import Protocol

from .audit import AuditLog
from .models import Approval, LoanApplication, LoanStatus
from .policy import PolicyConfig
from .repository import LocalRepository


class CreditScoreUnavailable(ValueError):
    """Raised when the approved bureau provider cannot return a score."""


@dataclass(frozen=True)
class CreditScoreResult:
    score: int | None
    band: str
    provider: str
    reference: str
    checked_at: str


class CreditBureauProvider(Protocol):
    def fetch_score(
        self,
        pan: str,
        consent_recorded: bool,
        application_id: str,
        *,
        consent_version: str,
        consent_purpose: str,
    ) -> CreditScoreResult: ...


class LocalCreditBureauDatabase:
    """Stores fictional score fixtures and a hashed lookup audit for local use."""

    pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

    def __init__(self, db_path: str | Path, hash_key: str | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.hash_key = (hash_key or os.getenv("CREDIT_BUREAU_HASH_KEY") or "local-demo-key-not-for-production").encode("utf-8")
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS credit_score_fixture (
                    subject_hash TEXT PRIMARY KEY,
                    score INTEGER CHECK (score BETWEEN 300 AND 900),
                    no_history INTEGER NOT NULL DEFAULT 0,
                    bureau_reference TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credit_score_check (
                    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id TEXT NOT NULL,
                    subject_hash TEXT NOT NULL,
                    score INTEGER,
                    band TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    bureau_reference TEXT NOT NULL,
                    consent_recorded INTEGER NOT NULL,
                    consent_version TEXT NOT NULL DEFAULT '',
                    consent_purpose TEXT NOT NULL DEFAULT '',
                    checked_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_credit_check_application
                    ON credit_score_check(application_id, checked_at);
                """
            )
            # Keep existing local databases usable after consent evidence was
            # added. SQLite cannot add both columns in the CREATE statement to
            # an already-created table, so migrate them explicitly.
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(credit_score_check)").fetchall()
            }
            if "consent_version" not in columns:
                connection.execute(
                    "ALTER TABLE credit_score_check ADD COLUMN consent_version TEXT NOT NULL DEFAULT ''"
                )
            if "consent_purpose" not in columns:
                connection.execute(
                    "ALTER TABLE credit_score_check ADD COLUMN consent_purpose TEXT NOT NULL DEFAULT ''"
                )

    def subject_hash(self, pan: str) -> str:
        normalized = pan.upper().strip()
        if not self.pan_pattern.fullmatch(normalized):
            raise ValueError("PAN format is invalid for the credit-bureau lookup.")
        return hmac.new(self.hash_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()

    def seed_fixture(self, pan: str, score: int | None, reference: str) -> None:
        if score is not None and not 300 <= score <= 900:
            raise ValueError("A CIBIL-style score must be between 300 and 900.")
        subject_hash = self.subject_hash(pan)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO credit_score_fixture(subject_hash, score, no_history, bureau_reference, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(subject_hash) DO UPDATE SET
                    score=excluded.score, no_history=excluded.no_history,
                    bureau_reference=excluded.bureau_reference, updated_at=excluded.updated_at
                """,
                (subject_hash, score, int(score is None), reference, datetime.now(timezone.utc).isoformat()),
            )

    def lookup(self, pan: str) -> sqlite3.Row | None:
        subject_hash = self.subject_hash(pan)
        with self._connection() as connection:
            return connection.execute(
                "SELECT subject_hash, score, no_history, bureau_reference FROM credit_score_fixture WHERE subject_hash=?",
                (subject_hash,),
            ).fetchone()

    def record_check(
        self,
        application_id: str,
        subject_hash: str,
        result: CreditScoreResult,
        consent_recorded: bool,
        consent_version: str,
        consent_purpose: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO credit_score_check(
                    application_id, subject_hash, score, band, provider,
                    bureau_reference, consent_recorded, consent_version,
                    consent_purpose, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    subject_hash,
                    result.score,
                    result.band,
                    result.provider,
                    result.reference,
                    int(consent_recorded),
                    consent_version,
                    consent_purpose,
                    result.checked_at,
                ),
            )


class LocalCreditBureauProvider:
    """Fetches a fictional test score from the local fixture database."""

    provider_name = "LOCAL_CIBIL_STYLE_FIXTURE"

    def __init__(self, database: LocalCreditBureauDatabase, policy: PolicyConfig) -> None:
        self.database = database
        self.policy = policy

    def fetch_score(
        self,
        pan: str,
        consent_recorded: bool,
        application_id: str,
        *,
        consent_version: str,
        consent_purpose: str,
    ) -> CreditScoreResult:
        if not consent_recorded:
            raise ValueError("Explicit consent is required before obtaining credit information.")
        row = self.database.lookup(pan)
        if row is None:
            raise CreditScoreUnavailable(
                "No local credit-bureau fixture exists for this PAN. Configure the authorised bank provider or add a fictional development fixture."
            )
        score = int(row["score"]) if row["score"] is not None else None
        if score is None:
            band = "NO_HISTORY"
        elif score < self.policy.credit_score_reject_below:
            band = "LOW"
        elif score < self.policy.credit_score_proceed_at_or_above:
            band = "REVIEW"
        else:
            band = "HIGH"
        result = CreditScoreResult(
            score,
            band,
            self.provider_name,
            row["bureau_reference"],
            datetime.now(timezone.utc).isoformat(),
        )
        self.database.record_check(
            application_id,
            self.database.subject_hash(pan),
            result,
            consent_recorded,
            consent_version,
            consent_purpose,
        )
        return result


class CreditBureauDecisionAgent:
    """Applies versioned bank thresholds after an authorised score lookup."""

    supported_consent_version = "CREDIT_BUREAU_CONSENT_V1"
    consent_purpose = "LOAN_ELIGIBILITY_AND_CREDIT_RISK_ASSESSMENT"

    def __init__(
        self,
        repository: LocalRepository,
        audit: AuditLog,
        policy: PolicyConfig,
        provider: CreditBureauProvider,
    ) -> None:
        self.repository = repository
        self.audit = audit
        self.policy = policy
        self.provider = provider

    def assess(
        self,
        application_id: str,
        pan: str,
        consent_recorded: bool,
        consent_version: str = supported_consent_version,
    ) -> LoanApplication:
        loan = self.repository.get_loan(application_id)
        if not consent_recorded:
            raise ValueError("Explicit consent is required before obtaining credit information.")
        if consent_version != self.supported_consent_version:
            raise ValueError("The credit-bureau consent version is unsupported or expired.")
        consent_recorded_at = datetime.now(timezone.utc).isoformat()
        loan.credit_bureau_consent_version = consent_version
        loan.credit_bureau_consent_recorded_at = consent_recorded_at
        loan.credit_bureau_consent_purpose = self.consent_purpose
        self.repository.save_loan(loan)
        self.audit.write(
            "credit-bureau-agent",
            "credit_bureau.consent_recorded",
            loan.application_id,
            "SUCCESS",
            {
                "consent_version": consent_version,
                "consent_purpose": self.consent_purpose,
                "recorded_at": consent_recorded_at,
            },
        )
        result = self.provider.fetch_score(
            pan,
            consent_recorded,
            application_id,
            consent_version=consent_version,
            consent_purpose=self.consent_purpose,
        )
        loan.credit_score = result.score
        loan.credit_score_band = result.band
        loan.credit_score_provider = result.provider
        loan.credit_score_reference = result.reference
        loan.credit_score_checked_at = result.checked_at

        audit_detail = {
            "score": result.score,
            "band": result.band,
            "provider": result.provider,
            "reference": result.reference,
            "reject_below": self.policy.credit_score_reject_below,
            "proceed_at_or_above": self.policy.credit_score_proceed_at_or_above,
        }
        if result.score is not None and result.score < self.policy.credit_score_reject_below and self.policy.auto_reject_low_credit_score:
            loan.status = LoanStatus.REJECTED.value
            loan.credit_score_decision = "REJECTED_LOW_SCORE"
            loan.diagnosis = (
                f"Credit score {result.score} is below the configured minimum "
                f"{self.policy.credit_score_reject_below}. The customer may request review or correct disputed bureau data."
            )
            outcome = "REJECTED"
        elif result.score is None or result.score < self.policy.credit_score_proceed_at_or_above:
            approval = self.repository.create_approval(
                Approval(
                    approval_id=f"APR-{len(self.repository.list_approvals()) + 1:04d}",
                    kind="CREDIT_SCORE_REVIEW",
                    entity_id=loan.application_id,
                    required_role="credit.manager",
                    package={**audit_detail, "reason": "No score or intermediate score requires authorised review"},
                )
            )
            loan.status = LoanStatus.AWAITING_APPROVAL.value
            loan.credit_score_decision = "HUMAN_REVIEW"
            loan.diagnosis = f"Credit profile requires Credit Manager review ({approval.approval_id})."
            audit_detail["approval_id"] = approval.approval_id
            outcome = "PENDING"
        else:
            loan.status = LoanStatus.HELD.value
            loan.credit_score_decision = "PROCEED_TO_WORKFLOW"
            loan.diagnosis = "Credit score met the configured proceed threshold; continuing loan checks."
            outcome = "SUCCESS"

        self.repository.save_loan(loan)
        self.audit.write("credit-bureau-agent", "credit_bureau.assessed", loan.application_id, outcome, audit_detail)
        return loan

    def route_unavailable(self, application_id: str) -> LoanApplication:
        """Keep provider/configuration failures out of automated rejection."""
        loan = self.repository.get_loan(application_id)
        approval = self.repository.create_approval(
            Approval(
                approval_id=f"APR-{len(self.repository.list_approvals()) + 1:04d}",
                kind="CREDIT_BUREAU_UNAVAILABLE",
                entity_id=loan.application_id,
                required_role="credit.manager",
                package={
                    "reason": "Credit-bureau result unavailable; manual retrieval or retry required",
                    "consent_version": loan.credit_bureau_consent_version,
                    "consent_purpose": loan.credit_bureau_consent_purpose,
                },
            )
        )
        loan.status = LoanStatus.AWAITING_APPROVAL.value
        loan.credit_score_decision = "HUMAN_REVIEW_BUREAU_UNAVAILABLE"
        loan.diagnosis = (
            f"Credit-bureau result is unavailable; routed to Credit Manager review "
            f"({approval.approval_id})."
        )
        self.repository.save_loan(loan)
        self.audit.write(
            "credit-bureau-agent",
            "credit_bureau.unavailable",
            loan.application_id,
            "PENDING",
            {"approval_id": approval.approval_id},
        )
        return loan
