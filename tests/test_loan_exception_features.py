import sqlite3
import tempfile
import unittest
from pathlib import Path

from banking_agents.audit import AuditLog
from banking_agents.loan_agent import LoanExceptionAgent
from banking_agents.loan_exception_platform import (
    DocumentIntelligenceService,
    LoanExceptionDatabase,
    PolicyVarianceSandbox,
)
from banking_agents.models import LoanApplication
from banking_agents.policy import PolicyConfig
from banking_agents.repository import LocalRepository


class LoanExceptionPlatformTests(unittest.TestCase):
    def test_document_intelligence_flags_incomplete_documents(self):
        service = DocumentIntelligenceService()
        result = service.pre_screen_document(
            "salary-slip.pdf",
            "Income statement for John Doe\nPlease sign below\nMissing page 2",
            document_type="PAYSLIP",
        )
        self.assertGreaterEqual(result.quality_score, 0)
        self.assertTrue(result.requires_human_review)
        self.assertIn("missing pages", " ".join(result.issues).lower())

    def test_policy_sandbox_auto_resolves_small_variance(self):
        sandbox = PolicyVarianceSandbox(tolerance_ratio=0.1)
        decision = sandbox.evaluate_variance(1200.0, 1180.0)
        self.assertTrue(decision.safe_to_auto_adjust)
        self.assertEqual(decision.action, "AUTO_RESOLVE")

    def test_database_architecture_persists_case_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cases.sqlite3"
            db = LoanExceptionDatabase(db_path)
            case_id = db.create_case("LN-1009", "MISSING_DOCUMENT", customer_name="Jane Doe")
            db.save_document(case_id, "PAN", "pan.pdf", "Name Jane Doe", 82, ["signature present"], {"name": "Jane Doe"}, False)
            db.save_policy_decision(case_id, 320.0, 0.05, "AUTO_RESOLVE", "Within tolerance")
            self.assertEqual(db.case_count(), 1)
            self.assertEqual(db.document_count(case_id), 1)

    def test_database_lists_recent_cases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cases.sqlite3"
            db = LoanExceptionDatabase(db_path)
            case_id = db.create_case("LN-1009", "MISSING_DOCUMENT", customer_name="Jane Doe")
            db.save_policy_decision(case_id, 320.0, 0.05, "AUTO_RESOLVE", "Within tolerance")
            rows = db.list_cases(limit=5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["application_id"], "LN-1009")
            self.assertEqual(rows[0]["action"], "AUTO_RESOLVE")

    def test_loan_agent_persists_exception_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = LocalRepository(root / "state.json")
            audit = AuditLog(root / "audit.jsonl")
            policy = PolicyConfig()
            repo.seed([
                LoanApplication("L-2001", "INCOME_VARIANCE", declared_income=1000.0, verified_income=900.0, documents=["income.pdf"], document_evidence={"PAN": "VALID"})
            ], [])
            db_path = root / "loan_cases.sqlite3"

            agent = LoanExceptionAgent(repo, audit, policy, exception_db_path=db_path)
            agent.run("L-2001")

            conn = sqlite3.connect(db_path)
            try:
                case_count = conn.execute("SELECT COUNT(*) FROM loan_exception_cases").fetchone()[0]
                policy_count = conn.execute("SELECT COUNT(*) FROM loan_exception_policy_decisions").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(case_count, 1)
            self.assertEqual(policy_count, 1)


if __name__ == "__main__":
    unittest.main()
