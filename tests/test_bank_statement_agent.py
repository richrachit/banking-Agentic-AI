import tempfile
import unittest
from pathlib import Path
from banking_agents.bank_statement_agent import BankStatementAnalysisAgent, BankStatementDatabase, StatementHeader, Transaction, VerificationEvidence


class BankStatementAgentTests(unittest.TestCase):
    def test_analysis_deduplicates_categorizes_and_flags_risk(self):
        agent = BankStatementAnalysisAgent(large_deposit_threshold=100000)
        header = StatementHeader("Customer", "XXXX1111", "IFSC1", "Bank", "Branch", "2026-01-01", "2026-01-31")
        duplicate = Transaction("2026-01-01", " Salary   NEFT ", credit=150000, running_balance=150000, reference_number="R1")
        result = agent.analyze("B1", header, [duplicate, duplicate, Transaction("2026-01-02", "Vendor payment UPI", debit=140000, running_balance=10000, reference_number="R2")], VerificationEvidence("C1", "2026-01-01T00:00:00+00:00", itr_reported_income=300000))
        self.assertEqual(len(result.transactions), 2); self.assertEqual(result.transactions[0].category, "SALARY")
        self.assertTrue({"LARGE_DEPOSIT", "RAPID_MOVEMENT"}.issubset({item["type"] for item in result.fraud_indicators})); self.assertTrue(result.human_review_required)

    def test_sqlite_persists_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            db = BankStatementDatabase(Path(temp) / "analysis.sqlite3")
            result = BankStatementAnalysisAgent().analyze("B2", StatementHeader("C", "XX12", "", "B", "", "2026-01-01", "2026-01-31"), [Transaction("2026-01-01", "Salary", credit=100, running_balance=100)], VerificationEvidence("C2", "2026-01-01T00:00:00+00:00"))
            db.save_analysis("CUST", result); self.assertEqual(db.get_analysis("B2")["analysis_id"], "B2")


if __name__ == "__main__": unittest.main()
