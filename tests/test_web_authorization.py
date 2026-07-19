import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from banking_agents.audit import AuditLog
from banking_agents.dormancy_agent import DormancyAgent
from banking_agents.loan_agent import LoanExceptionAgent
from banking_agents.models import Account, Approval, DormancyStatus, LoanApplication
from banking_agents.policy import PolicyConfig
from banking_agents.repository import LocalRepository
from banking_agents.web_app import BankingAppHandler, SESSIONS


class WebAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = LocalRepository(self.root / "state.json")
        self.audit = AuditLog(self.root / "audit.jsonl")
        policy = PolicyConfig()
        self.loan_agent = LoanExceptionAgent(
            self.repository,
            self.audit,
            policy,
            exception_db_path=self.root / "loan_cases.sqlite3",
        )
        self.dormancy_agent = DormancyAgent(
            self.repository,
            self.audit,
            policy,
            dormancy_db_path=self.root / "dormancy_cases.sqlite3",
        )
        self.services = (
            self.repository,
            self.audit,
            self.loan_agent,
            self.dormancy_agent,
        )
        self.token = "test-customer-session"
        SESSIONS[self.token] = ("CUSTOMER", "Customer One", "customer.one", "CUST-1")
        self.handler = object.__new__(BankingAppHandler)
        self.handler.headers = {"Cookie": f"banking_session={self.token}"}
        self.pages: list[str] = []
        self.handler._send = self.pages.append

    def tearDown(self):
        SESSIONS.clear()
        self.temp.cleanup()

    def test_customer_dashboard_and_detail_include_only_owned_loans(self):
        self.repository.save_loan(
            LoanApplication(
                "LOAN-OWN",
                "MISSING_DOCUMENT",
                applicant_name="Owned Customer",
                relationship_manager="customer-self-service",
                submitted_by="customer.one",
            )
        )
        self.repository.save_loan(
            LoanApplication(
                "LOAN-OTHER",
                "MISSING_DOCUMENT",
                applicant_name="Other Customer",
                relationship_manager="customer-self-service",
                submitted_by="customer.two",
            )
        )
        self.repository.create_approval(
            Approval("APR-SECRET", "UNCLAIMED_TRANSFER", "ACCOUNT-X", "compliance.officer", {"balance": 1000})
        )
        with patch("banking_agents.web_app.services", return_value=self.services):
            self.handler._dashboard("Ready", "CUSTOMER", "Customer One")
            dashboard = self.pages.pop()
            self.assertIn("LOAN-OWN", dashboard)
            self.assertNotIn("LOAN-OTHER", dashboard)
            self.assertNotIn("APR-SECRET", dashboard)
            self.assertNotIn("name='customer_id'", dashboard)

            self.handler._render_loan_detail("LOAN-OTHER")
            self.assertIn("Application not found", self.pages.pop())
            self.handler._render_loan_detail("LOAN-OWN")
            self.assertIn("Owned Customer", self.pages.pop())

    def test_customer_reactivation_uses_session_customer_id(self):
        self.repository.save_account(
            Account(
                "ACCOUNT-OWN",
                "CUST-1",
                "IN-RBI-DEA",
                250,
                "2010-01-01",
                status=DormancyStatus.DORMANT.value,
            )
        )
        self.repository.save_account(
            Account(
                "ACCOUNT-OTHER",
                "CUST-2",
                "IN-RBI-DEA",
                500,
                "2010-01-01",
                status=DormancyStatus.DORMANT.value,
            )
        )
        with patch("banking_agents.web_app.services", return_value=self.services):
            message = self.handler._action(
                "customer_dormant_request",
                {"account_id": ["ACCOUNT-OWN"], "kyc_confirmed": ["YES"]},
                "CUSTOMER",
                {},
            )
            self.assertIn("submitted", message)
            with self.assertRaisesRegex(ValueError, "not found"):
                self.handler._action(
                    "customer_dormant_request",
                    {"account_id": ["ACCOUNT-OTHER"], "kyc_confirmed": ["YES"]},
                    "CUSTOMER",
                    {},
                )

    def test_compliance_cannot_open_loan_detail_or_use_review_action(self):
        self.repository.save_loan(LoanApplication("LOAN-1", "MISSING_DOCUMENT"))
        SESSIONS[self.token] = (
            "COMPLIANCE",
            "Compliance Officer",
            "compliance.officer",
            "",
        )
        with patch("banking_agents.web_app.services", return_value=self.services):
            self.handler._render_loan_detail("LOAN-1")
            self.assertIn("Application not found", self.pages.pop())
            with self.assertRaisesRegex(ValueError, "not authorized"):
                self.handler._action(
                    "loan_review_action",
                    {
                        "application_id": ["LOAN-1"],
                        "review_action": ["APPROVE"],
                        "review_note": ["Should not work"],
                    },
                    "COMPLIANCE",
                    {},
                )

    def test_credit_decision_resumes_the_web_loan_workflow(self):
        self.repository.save_loan(
            LoanApplication(
                "LOAN-CREDIT",
                "MISSING_DOCUMENT",
                status="AWAITING_APPROVAL",
                credit_score=710,
                credit_score_decision="HUMAN_REVIEW",
                submitted_by="customer.one",
            )
        )
        self.repository.create_approval(
            Approval(
                "APR-CREDIT",
                "CREDIT_SCORE_REVIEW",
                "LOAN-CREDIT",
                "credit.manager",
                {"reason": "Intermediate score"},
            )
        )
        SESSIONS[self.token] = (
            "CREDIT",
            "Credit Manager",
            "credit.manager",
            "",
        )
        with patch("banking_agents.web_app.services", return_value=self.services):
            message = self.handler._action(
                "credit_decision",
                {
                    "approval_id": ["APR-CREDIT"],
                    "decision": ["APPROVED"],
                    "note": ["Bureau file manually reviewed."],
                },
                "CREDIT",
                {},
            )
        self.assertIn("workflow was updated", message)
        loan = self.repository.get_loan("LOAN-CREDIT")
        self.assertEqual(loan.status, "AWAITING_CUSTOMER")
        self.assertEqual(loan.credit_score_decision, "HUMAN_REVIEW_APPROVED")


if __name__ == "__main__":
    unittest.main()
