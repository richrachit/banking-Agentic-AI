from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class IncentiveResult:
    tier: str
    amount: float
    rationale: str


class DormancyIncentiveCalculator:
    """Calculates RBI-style incentive values for dormant accounts."""

    def calculate_incentive(self, balance: float, idle_days: int) -> IncentiveResult:
        if idle_days < 365:
            return IncentiveResult("BELOW_THRESHOLD", 0.0, "Account is not yet in the accelerated payout window")
        if idle_days < 365 * 10:
            amount = min(balance * 0.05, 5000.0)
            return IncentiveResult("UP_TO_4_YEARS", amount, "Up to 4 years idle")
        amount = min(balance * 0.075, 25000.0)
        return IncentiveResult("OVER_10_YEARS", amount, "Over 10 years idle")


class DormancyCaseDatabase:
    """SQLite-backed persistence layer for dormant-account and escheatment workflows."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dormancy_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    balance REAL NOT NULL,
                    inactivity_days INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dormancy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES dormancy_cases(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dormancy_outreach (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES dormancy_cases(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dormancy_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    trace_type TEXT NOT NULL,
                    result TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES dormancy_cases(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dormancy_filings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    filing_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES dormancy_cases(id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_case(self, account_id: str, customer_id: str, jurisdiction: str, balance: float, last_activity: date, inactivity_days: int) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "INSERT INTO dormancy_cases(account_id, customer_id, jurisdiction, balance, inactivity_days) VALUES (?, ?, ?, ?, ?)",
                (account_id, customer_id, jurisdiction, balance, inactivity_days),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def record_event(self, case_id: int, event_type: str, details: str | None = None) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT INTO dormancy_events(case_id, event_type, details) VALUES (?, ?, ?)", (case_id, event_type, details))
            conn.commit()
        finally:
            conn.close()

    def record_outreach(self, case_id: int, channel: str, status: str, note: str | None = None) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT INTO dormancy_outreach(case_id, channel, status, note) VALUES (?, ?, ?, ?)", (case_id, channel, status, note))
            conn.commit()
        finally:
            conn.close()

    def record_trace(self, case_id: int, source: str, trace_type: str, result: str, status: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT INTO dormancy_traces(case_id, source, trace_type, result, status) VALUES (?, ?, ?, ?, ?)", (case_id, source, trace_type, result, status))
            conn.commit()
        finally:
            conn.close()

    def record_filing(self, case_id: int, filing_type: str, status: str, note: str | None = None) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT INTO dormancy_filings(case_id, filing_type, status, note) VALUES (?, ?, ?, ?)", (case_id, filing_type, status, note))
            conn.commit()
        finally:
            conn.close()

    def list_cases(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, account_id, customer_id, jurisdiction, balance, inactivity_days, status, created_at
                FROM dormancy_cases
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "id": case_id,
                    "account_id": account_id,
                    "customer_id": customer_id,
                    "jurisdiction": jurisdiction,
                    "balance": balance,
                    "inactivity_days": inactivity_days,
                    "status": status,
                    "created_at": created_at,
                }
                for case_id, account_id, customer_id, jurisdiction, balance, inactivity_days, status, created_at in rows
            ]
        finally:
            conn.close()
