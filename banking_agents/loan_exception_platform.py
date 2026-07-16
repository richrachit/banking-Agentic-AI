from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DocumentValidationResult:
    document_name: str
    quality_score: int
    issues: list[str] = field(default_factory=list)
    requires_human_review: bool = False


@dataclass
class PolicyDecision:
    declared_income: float
    verified_income: float
    ratio: float
    safe_to_auto_adjust: bool
    action: str
    rationale: str


class DocumentIntelligenceService:
    """Lightweight document pre-screening for loan exception workflows."""

    def pre_screen_document(self, document_name: str, text: str, document_type: str = "UNKNOWN") -> DocumentValidationResult:
        issues: list[str] = []
        lower_text = text.lower()
        if "missing page" in lower_text or "page 2" in lower_text:
            issues.append("missing pages")
        if "signature" in lower_text and "missing" in lower_text:
            issues.append("signature incomplete")
        if "illegible" in lower_text or "blur" in lower_text:
            issues.append("blurred or illegible content")
        if not text.strip():
            issues.append("empty document")

        quality_score = max(0, 100 - (len(issues) * 20))
        requires_human_review = bool(issues) or quality_score < 70
        return DocumentValidationResult(document_name=document_name, quality_score=quality_score, issues=issues, requires_human_review=requires_human_review)


class PolicyVarianceSandbox:
    """Evaluates whether a variance is safe to auto-adjust under policy rules."""

    def __init__(self, tolerance_ratio: float = 0.1) -> None:
        self.tolerance_ratio = tolerance_ratio

    def evaluate_variance(self, declared_income: float, verified_income: float) -> PolicyDecision:
        if declared_income <= 0:
            return PolicyDecision(declared_income, verified_income, 0.0, False, "REJECT", "Declared income must be positive")
        ratio = abs(declared_income - verified_income) / declared_income
        if ratio <= self.tolerance_ratio:
            return PolicyDecision(declared_income, verified_income, ratio, True, "AUTO_RESOLVE", "Variance within safe threshold")
        return PolicyDecision(declared_income, verified_income, ratio, False, "ESCALATE", "Variance exceeds threshold")


class LoanExceptionDatabase:
    """Small SQLite schema to persist loan exception cases and supporting artifacts."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loan_exception_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id TEXT UNIQUE NOT NULL,
                    exception_code TEXT NOT NULL,
                    customer_name TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loan_exception_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    document_type TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    extracted_text TEXT,
                    quality_score INTEGER,
                    issues TEXT,
                    metadata TEXT,
                    requires_human_review INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(case_id) REFERENCES loan_exception_cases(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loan_exception_policy_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    declared_income REAL NOT NULL,
                    verified_income REAL NOT NULL,
                    ratio REAL NOT NULL,
                    action TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES loan_exception_cases(id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_case(self, application_id: str, exception_code: str, customer_name: str | None = None) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            existing = conn.execute("SELECT id FROM loan_exception_cases WHERE application_id = ?", (application_id,)).fetchone()
            if existing:
                return int(existing[0])
            cursor = conn.execute("INSERT INTO loan_exception_cases(application_id, exception_code, customer_name) VALUES (?, ?, ?)", (application_id, exception_code, customer_name))
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def save_document(self, case_id: int, document_type: str, file_name: str, extracted_text: str, quality_score: int, issues: list[str], metadata: dict[str, Any], requires_human_review: bool) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO loan_exception_documents(case_id, document_type, file_name, extracted_text, quality_score, issues, metadata, requires_human_review) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, document_type, file_name, extracted_text, quality_score, "|".join(issues), repr(metadata), int(requires_human_review)),
            )
            conn.commit()
        finally:
            conn.close()

    def save_policy_decision(self, case_id: int, declared_income: float, verified_income: float, action: str, rationale: str) -> None:
        ratio = abs(declared_income - verified_income) / declared_income if declared_income else 0.0
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO loan_exception_policy_decisions(case_id, declared_income, verified_income, ratio, action, rationale) VALUES (?, ?, ?, ?, ?, ?)",
                (case_id, declared_income, verified_income, ratio, action, rationale),
            )
            conn.commit()
        finally:
            conn.close()

    def case_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM loan_exception_cases").fetchone()[0])
        finally:
            conn.close()

    def document_count(self, case_id: int) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM loan_exception_documents WHERE case_id = ?", (case_id,)).fetchone()[0])
        finally:
            conn.close()

    def list_cases(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT
                    lc.application_id,
                    lc.exception_code,
                    lc.customer_name,
                    lc.status,
                    lc.created_at,
                    lpd.action,
                    lpd.rationale
                FROM loan_exception_cases lc
                LEFT JOIN loan_exception_policy_decisions lpd ON lpd.case_id = lc.id
                ORDER BY lc.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "application_id": application_id,
                    "exception_code": exception_code,
                    "customer_name": customer_name,
                    "status": status,
                    "created_at": created_at,
                    "action": action,
                    "rationale": rationale,
                }
                for application_id, exception_code, customer_name, status, created_at, action, rationale in rows
            ]
        finally:
            conn.close()
