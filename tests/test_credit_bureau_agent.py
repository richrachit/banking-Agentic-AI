import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import sqlite3

from banking_agents.audit import AuditLog
from banking_agents.credit_bureau_agent import CreditBureauDecisionAgent, LocalCreditBureauDatabase, LocalCreditBureauProvider
from banking_agents.loan_agent import LoanExceptionAgent
from banking_agents.loan_origination import LoanOriginationService
from banking_agents.models import LoanApplication, LoanStatus
from banking_agents.policy import PolicyConfig
from banking_agents.repository import LocalRepository


class CreditBureauAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = LocalRepository(self.root / "state.json")
        self.audit = AuditLog(self.root / "audit.jsonl")
        self.policy = PolicyConfig()
        self.database = LocalCreditBureauDatabase(self.root / "credit.sqlite3", hash_key="test-key")
        self.database.seed_fixture("DEMOA0001A", 790, "HIGH")
        self.database.seed_fixture("DEMOB0002B", 710, "REVIEW")
        self.database.seed_fixture("DEMOC0003C", 580, "LOW")
        self.database.seed_fixture("DEMOD0004D", None, "NO-HISTORY")
        self.provider = LocalCreditBureauProvider(self.database, self.policy)
        self.agent = CreditBureauDecisionAgent(self.repo, self.audit, self.policy, self.provider)

    def tearDown(self):
        self.temp.cleanup()

    def save_loan(self, application_id):
        loan = LoanApplication(application_id, "MISSING_DOCUMENT")
        self.repo.save_loan(loan)

    def test_high_score_continues_existing_workflow(self):
        self.save_loan("L-HIGH")
        loan_agent = LoanExceptionAgent(self.repo, self.audit, self.policy, exception_db_path=self.root / "loan.sqlite3")
        output = LoanOriginationService(self.repo, loan_agent, self.agent).submit(
            self.repo.get_loan("L-HIGH"), "DEMOA0001A", True
        )
        self.assertEqual(output.credit_score, 790)
        self.assertEqual(output.credit_score_decision, "PROCEED_TO_WORKFLOW")
        self.assertEqual(output.status, LoanStatus.AWAITING_CUSTOMER.value)

    def test_low_score_uses_explainable_rejection_path(self):
        self.save_loan("L-LOW")
        output = self.agent.assess("L-LOW", "DEMOC0003C", True)
        self.assertEqual(output.status, LoanStatus.REJECTED.value)
        self.assertEqual(output.credit_score_decision, "REJECTED_LOW_SCORE")
        self.assertIn("configured minimum", output.diagnosis)

    def test_intermediate_and_no_history_route_to_credit_manager(self):
        for application_id, pan in (("L-REVIEW", "DEMOB0002B"), ("L-NH", "DEMOD0004D")):
            self.save_loan(application_id)
            output = self.agent.assess(application_id, pan, True)
            self.assertEqual(output.status, LoanStatus.AWAITING_APPROVAL.value)
        self.assertEqual(len(self.repo.list_approvals()), 2)
        self.assertTrue(all(item.required_role == "credit.manager" for item in self.repo.list_approvals()))

    def test_lookup_requires_consent_and_does_not_store_raw_pan(self):
        self.save_loan("L-CONSENT")
        with self.assertRaisesRegex(ValueError, "consent"):
            self.agent.assess("L-CONSENT", "DEMOA0001A", False)
        self.assertNotIn(b"DEMOA0001A", self.database.db_path.read_bytes())

    def test_consent_version_and_purpose_are_stored_with_check(self):
        self.save_loan("L-CONSENT-EVIDENCE")
        output = self.agent.assess(
            "L-CONSENT-EVIDENCE",
            "DEMOA0001A",
            True,
            "CREDIT_BUREAU_CONSENT_V1",
        )
        self.assertEqual(output.credit_bureau_consent_version, "CREDIT_BUREAU_CONSENT_V1")
        self.assertTrue(output.credit_bureau_consent_recorded_at)
        with closing(sqlite3.connect(self.database.db_path)) as connection:
            evidence = connection.execute(
                "SELECT consent_recorded, consent_version, consent_purpose FROM credit_score_check"
            ).fetchone()
        self.assertEqual(
            evidence,
            (1, "CREDIT_BUREAU_CONSENT_V1", "LOAN_ELIGIBILITY_AND_CREDIT_RISK_ASSESSMENT"),
        )

    def test_unavailable_provider_fixture_routes_to_human_without_rejection(self):
        self.save_loan("L-UNAVAILABLE")
        loan_agent = LoanExceptionAgent(self.repo, self.audit, self.policy, exception_db_path=self.root / "loan.sqlite3")
        output = LoanOriginationService(self.repo, loan_agent, self.agent).submit(
            self.repo.get_loan("L-UNAVAILABLE"), "ABCDE1234F", True
        )
        self.assertEqual(output.status, LoanStatus.AWAITING_APPROVAL.value)
        self.assertEqual(output.credit_score_decision, "HUMAN_REVIEW_BUREAU_UNAVAILABLE")
        approval = self.repo.list_approvals()[0]
        self.assertEqual(approval.kind, "CREDIT_BUREAU_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
