import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from banking_agents.audit import AuditLog
from banking_agents.dormancy_agent import DormancyAgent
from banking_agents.dormancy_escheatment_platform import DormancyCaseDatabase, DormancyIncentiveCalculator
from banking_agents.models import Account
from banking_agents.policy import PolicyConfig
from banking_agents.repository import LocalRepository


class DormancyDatabaseTests(unittest.TestCase):
    def test_incentive_calculator_applies_expected_caps(self):
        calculator = DormancyIncentiveCalculator()
        short_term = calculator.calculate_incentive(balance=100000.0, idle_days=365 * 3)
        long_term = calculator.calculate_incentive(balance=1000000.0, idle_days=365 * 12)
        self.assertEqual(short_term.amount, 5000.0)
        self.assertEqual(long_term.amount, 25000.0)
        self.assertEqual(long_term.tier, "OVER_10_YEARS")

    def test_database_persists_case_and_related_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "dormancy.sqlite3"
            db = DormancyCaseDatabase(db_path)
            case_id = db.create_case("A-100", "C-100", "IN-RBI-DEA", 100000.0, date(2025, 1, 1), 365 * 5)
            db.record_event(case_id, "OUTREACH_STARTED", "sms sent")
            db.record_outreach(case_id, "SMS", "SENT", "customer acknowledged")
            db.record_trace(case_id, "SECONDARY_DB", "ADDRESS_TRACE", "updated phone", "MATCHED")
            db.record_filing(case_id, "DEA_REPORT", "PENDING", "report package ready")
            rows = db.list_cases(limit=5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["account_id"], "A-100")
            self.assertEqual(rows[0]["status"], "OPEN")

    def test_dormancy_agent_persists_case_when_account_becomes_dormant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = LocalRepository(root / "state.json")
            audit = AuditLog(root / "audit.jsonl")
            policy = PolicyConfig()
            repo.save_account(Account("A-200", "C-200", "IN-RBI-DEA", 120000.0, (date.today() - timedelta(days=4000)).isoformat()))
            db_path = root / "dormancy_cases.sqlite3"
            agent = DormancyAgent(repo, audit, policy, dormancy_db_path=db_path)
            agent.run(date.today())
            conn = sqlite3.connect(db_path)
            try:
                case_count = conn.execute("SELECT COUNT(*) FROM dormancy_cases").fetchone()[0]
                event_count = conn.execute("SELECT COUNT(*) FROM dormancy_events").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(case_count, 1)
            self.assertGreaterEqual(event_count, 1)


if __name__ == "__main__":
    unittest.main()
