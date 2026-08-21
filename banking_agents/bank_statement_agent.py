from __future__ import annotations

"""Explainable bank-statement and Account Aggregator analysis.

The agent consumes extracted transactions. PDF/image extraction is a provider
boundary: the local API extracts text from digital PDFs and otherwise routes the
document for OCR review. Calculations in this module never approve a loan.
"""

from dataclasses import asdict, dataclass, field
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any


@dataclass
class StatementHeader:
    customer_name: str
    account_number_masked: str
    ifsc_code: str
    bank_name: str
    branch_name: str
    period_start: str
    period_end: str


@dataclass
class Transaction:
    transaction_date: str
    narration: str
    debit: float = 0.0
    credit: float = 0.0
    running_balance: float = 0.0
    reference_number: str = ""
    transaction_mode: str = "OTHER"
    category: str = "UNCATEGORIZED"
    subcategory: str = ""


@dataclass
class VerificationEvidence:
    consent_id: str
    consented_at: str
    consent_purpose: str = "INCOME_AND_EMPLOYMENT_VERIFICATION"
    source: str = "DOCUMENT_UPLOAD"
    gst_reported_turnover: float | None = None
    itr_reported_income: float | None = None
    gst_filing_delays: int = 0
    itr_filing_delays: int = 0
    outstanding_tax_demand: float = 0.0


@dataclass
class StatementAnalysis:
    analysis_id: str
    header: StatementHeader
    transactions: list[Transaction]
    evidence: VerificationEvidence
    metrics: dict[str, Any]
    monthly: list[dict[str, Any]]
    category_totals: dict[str, float]
    fraud_indicators: list[dict[str, Any]]
    cross_validation: dict[str, Any]
    risk_score: int
    risk_level: str
    explanations: list[str] = field(default_factory=list)
    human_review_required: bool = True


class BankStatementDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS bank_statement_analysis (
                    analysis_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    consent_id TEXT NOT NULL,
                    document_sha256 TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bank_statement_transaction (
                    analysis_id TEXT NOT NULL,
                    transaction_key TEXT NOT NULL,
                    transaction_date TEXT NOT NULL,
                    narration TEXT NOT NULL,
                    debit REAL NOT NULL,
                    credit REAL NOT NULL,
                    running_balance REAL NOT NULL,
                    category TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    PRIMARY KEY (analysis_id, transaction_key),
                    FOREIGN KEY (analysis_id) REFERENCES bank_statement_analysis(analysis_id)
                );
                CREATE TABLE IF NOT EXISTS uploaded_financial_document (
                    document_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    password_protected INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
            """)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def save_document(self, document_id: str, customer_id: str, document_type: str, media_type: str, content: bytes, status: str, password_protected: bool) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO uploaded_financial_document VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, customer_id, document_type, media_type, len(content), hashlib.sha256(content).hexdigest(), status, int(password_protected), datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()

    def save_analysis(self, customer_id: str, analysis: StatementAnalysis, document_sha256: str = "") -> None:
        payload = json.dumps(asdict(analysis), sort_keys=True)
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO bank_statement_analysis VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (analysis.analysis_id, customer_id, analysis.evidence.source, analysis.evidence.consent_id, document_sha256, "REVIEW_REQUIRED", payload, datetime.now(timezone.utc).isoformat()),
            )
            connection.execute("DELETE FROM bank_statement_transaction WHERE analysis_id=?", (analysis.analysis_id,))
            for item in analysis.transactions:
                key = hashlib.sha256(json.dumps(asdict(item), sort_keys=True).encode()).hexdigest()
                connection.execute(
                    "INSERT INTO bank_statement_transaction VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (analysis.analysis_id, key, item.transaction_date, item.narration, item.debit, item.credit, item.running_balance, item.category, item.transaction_mode),
                )
            connection.commit()

    def get_analysis(self, analysis_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT payload_json FROM bank_statement_analysis WHERE analysis_id=?", (analysis_id,)).fetchone()
        if row is None:
            raise KeyError(analysis_id)
        return json.loads(row["payload_json"])


class BankStatementAnalysisAgent:
    CATEGORY_PATTERNS = {
        "SALARY": ("salary", "payroll", "wages"),
        "BUSINESS_INCOME": ("invoice", "business receipt", "sales", "merchant settlement"),
        "RENT": ("rent", "landlord"),
        "LOAN_EMI": ("emi", "loan repayment", "nach loan"),
        "UTILITY": ("electricity", "water bill", "gas bill", "utility"),
        "INSURANCE": ("insurance", "premium"),
        "INVESTMENT": ("mutual fund", "sip", "broker", "investment"),
        "GST": ("gst", "goods and services tax"),
        "TAX": ("income tax", "tds", "advance tax"),
        "VENDOR_PAYMENT": ("vendor", "supplier"),
        "CREDIT_CARD_PAYMENT": ("credit card", "card payment"),
        "REFUND": ("refund", "reversal"),
        "INTEREST": ("interest credit", "int.pd", "interest"),
        "CASH": ("cash deposit", "cash withdrawal", "atm"),
        "FUEL": ("fuel", "petrol", "diesel"),
        "SHOPPING": ("shopping", "store", "ecommerce"),
    }

    MODE_PATTERNS = ("UPI", "IMPS", "NEFT", "RTGS", "ATM", "CHEQUE", "NACH", "CASH")

    def __init__(self, large_deposit_threshold: float = 200000.0, rapid_movement_hours: int = 24) -> None:
        self.large_deposit_threshold = large_deposit_threshold
        self.rapid_movement_hours = rapid_movement_hours

    def analyze(self, analysis_id: str, header: StatementHeader, transactions: list[Transaction], evidence: VerificationEvidence) -> StatementAnalysis:
        cleaned = self._clean(transactions)
        categorized = [self._categorize(item) for item in cleaned]
        monthly = self._monthly(categorized)
        credits = sum(item.credit for item in categorized)
        debits = sum(item.debit for item in categorized)
        balances = [item.running_balance for item in categorized]
        income = [item.credit for item in categorized if item.category in {"SALARY", "BUSINESS_INCOME"}]
        monthly_emi = sum(item.debit for item in categorized if item.category in {"LOAN_EMI", "CREDIT_CARD_PAYMENT"}) / max(1, len(monthly))
        monthly_income = sum(income) / max(1, len(monthly))
        fraud = self._fraud(categorized)
        cross = self._cross_validate(categorized, evidence)
        category_totals: dict[str, float] = {}
        for item in categorized:
            category_totals[item.category] = round(category_totals.get(item.category, 0.0) + item.credit - item.debit, 2)
        metrics = {
            "opening_balance": categorized[0].running_balance - categorized[0].credit + categorized[0].debit if categorized else 0.0,
            "closing_balance": categorized[-1].running_balance if categorized else 0.0,
            "average_daily_balance": round(sum(balances) / len(balances), 2) if balances else 0.0,
            "minimum_balance": min(balances, default=0.0),
            "maximum_balance": max(balances, default=0.0),
            "total_credits": round(credits, 2),
            "total_debits": round(debits, 2),
            "net_cash_flow": round(credits - debits, 2),
            "average_monthly_income": round(monthly_income, 2),
            "highest_income_credit": max(income, default=0.0),
            "lowest_income_credit": min(income, default=0.0),
            "monthly_debt_obligation": round(monthly_emi, 2),
            "emi_to_income_ratio_percent": round(monthly_emi / monthly_income * 100, 2) if monthly_income else None,
            "cheque_bounces": sum(1 for item in categorized if re.search(r"\b(?:bounce|returned|nsf)\b", item.narration, re.I)),
        }
        risk = min(100, len(fraud) * 10 + evidence.gst_filing_delays * 5 + evidence.itr_filing_delays * 5 + (20 if evidence.outstanding_tax_demand > 0 else 0) + int(cross["variance_risk_points"]))
        explanations = [item["explanation"] for item in fraud] + list(cross["explanations"])
        return StatementAnalysis(analysis_id, header, categorized, evidence, metrics, monthly, category_totals, fraud, cross, risk, "HIGH" if risk >= 60 else "MEDIUM" if risk >= 30 else "LOW", explanations)

    def _clean(self, transactions: list[Transaction]) -> list[Transaction]:
        unique: dict[tuple[Any, ...], Transaction] = {}
        for item in transactions:
            parsed = date.fromisoformat(item.transaction_date)
            narration = re.sub(r"\s+", " ", item.narration).strip()
            cleaned = Transaction(parsed.isoformat(), narration, round(float(item.debit), 2), round(float(item.credit), 2), round(float(item.running_balance), 2), item.reference_number.strip(), item.transaction_mode.upper().strip())
            if cleaned.debit < 0 or cleaned.credit < 0 or (cleaned.debit and cleaned.credit):
                raise ValueError("Each transaction must contain one non-negative debit or credit amount.")
            key = (cleaned.transaction_date, cleaned.reference_number, cleaned.narration.lower(), cleaned.debit, cleaned.credit, cleaned.running_balance)
            unique.setdefault(key, cleaned)
        return sorted(unique.values(), key=lambda item: (item.transaction_date, item.reference_number, item.narration))

    def _categorize(self, item: Transaction) -> Transaction:
        lowered = item.narration.lower()
        for category, patterns in self.CATEGORY_PATTERNS.items():
            if any(pattern in lowered for pattern in patterns):
                item.category = category
                break
        for mode in self.MODE_PATTERNS:
            if mode.lower() in lowered:
                item.transaction_mode = mode
                break
        if item.category == "UNCATEGORIZED":
            item.category = "TRANSFER" if item.transaction_mode in {"UPI", "IMPS", "NEFT", "RTGS"} else "OTHER"
        return item

    @staticmethod
    def _monthly(items: list[Transaction]) -> list[dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            month = item.transaction_date[:7]
            row = result.setdefault(month, {"month": month, "credits": 0.0, "debits": 0.0, "closing_balance": 0.0})
            row["credits"] += item.credit; row["debits"] += item.debit; row["closing_balance"] = item.running_balance
        for row in result.values():
            row["credits"] = round(row["credits"], 2); row["debits"] = round(row["debits"], 2); row["net_cash_flow"] = round(row["credits"] - row["debits"], 2); row["status"] = "SURPLUS" if row["net_cash_flow"] >= 0 else "DEFICIT"
        return [result[key] for key in sorted(result)]

    def _fraud(self, items: list[Transaction]) -> list[dict[str, Any]]:
        flags: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            amount = item.credit or item.debit
            if item.credit >= self.large_deposit_threshold:
                flags.append({"type": "LARGE_DEPOSIT", "transaction_date": item.transaction_date, "amount": item.credit, "explanation": f"Credit exceeds configured threshold {self.large_deposit_threshold:.2f}."})
            if amount >= 10000 and amount % 10000 == 0:
                flags.append({"type": "ROUND_NUMBER", "transaction_date": item.transaction_date, "amount": amount, "explanation": "High-value round-number transaction requires source review."})
            if index + 1 < len(items):
                following = items[index + 1]
                if item.credit and following.debit and following.debit >= item.credit * 0.9 and date.fromisoformat(following.transaction_date) <= date.fromisoformat(item.transaction_date) + timedelta(days=1):
                    flags.append({"type": "RAPID_MOVEMENT", "transaction_date": item.transaction_date, "amount": item.credit, "explanation": "Most of a credit moved out within one day."})
        return flags

    @staticmethod
    def _cross_validate(items: list[Transaction], evidence: VerificationEvidence) -> dict[str, Any]:
        business_credits = sum(item.credit for item in items if item.category == "BUSINESS_INCOME")
        income_credits = sum(item.credit for item in items if item.category in {"BUSINESS_INCOME", "SALARY"})
        explanations: list[str] = []
        points = 0.0
        def variance(actual: float, reported: float | None, label: str) -> float | None:
            nonlocal points
            if reported is None or reported <= 0:
                return None
            value = abs(actual - reported) / reported
            if value > 0.20:
                points += min(30, value * 30)
                explanations.append(f"{label} differs from statement credits by {value * 100:.1f}%.")
            return round(value * 100, 2)
        return {
            "business_credits": round(business_credits, 2),
            "income_credits": round(income_credits, 2),
            "gst_turnover_variance_percent": variance(business_credits, evidence.gst_reported_turnover, "GST turnover"),
            "itr_income_variance_percent": variance(income_credits, evidence.itr_reported_income, "ITR income"),
            "gst_filing_delays": evidence.gst_filing_delays,
            "itr_filing_delays": evidence.itr_filing_delays,
            "outstanding_tax_demand": evidence.outstanding_tax_demand,
            "variance_risk_points": round(points, 2),
            "explanations": explanations,
        }
