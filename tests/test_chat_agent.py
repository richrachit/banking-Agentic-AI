import gc
import json
import tempfile
import unittest
from pathlib import Path

from banking_agents.auth_service import AuthenticatedUser
from banking_agents.chat_agent import BankingSupportChatAgent
from banking_agents.models import Account, Approval, DormancyStatus, LoanApplication
from banking_agents.repository import LocalRepository


class BankingSupportChatAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = LocalRepository(self.root / "state.json")
        self.repository.seed(
            [
                LoanApplication(
                    "LN-CUST-1",
                    "MISSING_DOCUMENT",
                    submitted_by="customer",
                    status="AWAITING_CUSTOMER",
                    diagnosis="A bank statement is required.",
                ),
                LoanApplication(
                    "LN-OTHER-1",
                    "INCOME_VARIANCE",
                    submitted_by="other.customer",
                    status="HELD",
                    diagnosis="Income requires review.",
                ),
            ],
            [
                Account(
                    "ACC-CUST-1",
                    "CUST-1",
                    "IN-RBI-DEA",
                    1200.0,
                    "2010-01-01",
                    status=DormancyStatus.DORMANT.value,
                ),
                Account(
                    "ACC-OTHER-1",
                    "CUST-OTHER",
                    "IN-RBI-DEA",
                    900.0,
                    "2010-01-01",
                    status=DormancyStatus.TRANSFER_PENDING.value,
                ),
            ],
        )
        self.repository.create_approval(
            Approval("APR-CREDIT", "CREDIT_SCORE_REVIEW", "LN-CUST-1", "credit.manager", {})
        )
        self.repository.create_approval(
            Approval("APR-COMPLIANCE", "UNCLAIMED_TRANSFER", "ACC-CUST-1", "compliance.officer", {})
        )
        self.agent = BankingSupportChatAgent(self.repository)
        self.customer = AuthenticatedUser("customer", "CUSTOMER", "Customer", "CUST-1")
        self.credit_manager = AuthenticatedUser("credit.manager", "CREDIT", "Credit Manager")
        self.compliance_officer = AuthenticatedUser("compliance.officer", "COMPLIANCE", "Compliance Officer")

    def tearDown(self):
        # The local SQLite runtime opens short-lived read connections. Force their
        # finalizers before TemporaryDirectory removes the database on Windows.
        gc.collect()
        self.temp.cleanup()

    def test_customer_chat_is_scoped_to_owned_loans_and_accounts(self):
        own_loan = self.agent.respond("What is the status of LN-CUST-1?", self.customer)
        self.assertEqual(own_loan.intent, "LOAN_STATUS")
        self.assertIn("LN-CUST-1", own_loan.reply)

        other_loan = self.agent.respond("What is the status of LN-OTHER-1?", self.customer)
        self.assertNotIn("LN-OTHER-1", other_loan.reply)
        self.assertIn("LN-CUST-1", other_loan.reply)

        other_account = self.agent.respond("How do I reactivate ACC-OTHER-1?", self.customer)
        self.assertEqual(other_account.intent, "DORMANCY_STATUS")
        self.assertNotIn("ACC-OTHER-1", other_account.reply)
        self.assertIn("1 account(s)", other_account.reply)
        self.assertIn("dormant", other_account.reply)

    def test_role_scopes_prevent_loan_and_approval_queue_leakage(self):
        loan_question = self.agent.respond("Show the latest loan status", self.compliance_officer)
        self.assertEqual(loan_question.intent, "LOAN_SCOPE")
        self.assertNotIn("LN-CUST-1", loan_question.reply)

        approvals = self.agent.respond("How many approvals are pending?", self.credit_manager)
        self.assertEqual(approvals.intent, "APPROVAL_QUEUE")
        self.assertIn("1 pending", approvals.reply)
        self.assertIn("credit score review", approvals.reply)
        self.assertNotIn("unclaimed transfer", approvals.reply)

    def test_mutating_request_is_refused_without_changing_workflow_data(self):
        before = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        result = self.agent.respond("Please approve my loan and transfer the money.", self.customer)
        after = json.loads((self.root / "state.json").read_text(encoding="utf-8"))

        self.assertEqual(result.intent, "ACTION_BOUNDARY")
        self.assertTrue(result.read_only)
        self.assertIn("cannot perform", result.reply)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
