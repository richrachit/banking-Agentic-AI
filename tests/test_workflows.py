import tempfile
import unittest
from datetime import date
from pathlib import Path

from banking_agents.audit import AuditLog
from banking_agents.automation_agent import OperationsAutomationAgent
from banking_agents.dormancy_agent import DormancyAgent
from banking_agents.document_verification import DocumentVerificationModel
from banking_agents.document_ai import BaselineDocumentAIProvider
from banking_agents.loan_agent import LoanExceptionAgent
from banking_agents.models import Account, Approval, LoanApplication, LoanStatus
from banking_agents.policy import PolicyConfig
from banking_agents.repository import LocalRepository


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.repo = LocalRepository(self.root / "state.json"); self.audit = AuditLog(self.root / "audit.jsonl"); self.policy = PolicyConfig()

    def loan_agent(self):
        return LoanExceptionAgent(self.repo, self.audit, self.policy, exception_db_path=self.root / "loan-cases.sqlite3")

    def dormancy_agent(self):
        return DormancyAgent(self.repo, self.audit, self.policy, dormancy_db_path=self.root / "dormancy-cases.sqlite3")

    def tearDown(self): self.temp.cleanup()

    def test_income_deviation_needs_then_applies_approval(self):
        self.repo.seed([LoanApplication("L1", "INCOME_VARIANCE", declared_income=100, verified_income=70)], [])
        agent = self.loan_agent()
        self.assertEqual(agent.run("L1").status, "AWAITING_APPROVAL")
        approval = self.repo.list_approvals()[0]; approval.status = "APPROVED"; self.repo.save_approval(approval)
        self.assertEqual(agent.apply_approved_deviation("L1").status, "READY_FOR_MAIN_JOURNEY")

    def test_dormant_account_requires_approval_before_transfer(self):
        self.repo.seed([], [Account("A1", "C1", "IN-RBI-DEA", 90, "2010-01-01")])
        agent = self.dormancy_agent(); agent.run(date(2026, 7, 15))
        self.assertEqual(self.repo.get_account("A1").status, "TRANSFER_PENDING")
        approval = self.repo.list_approvals()[0]; approval.status = "APPROVED"; self.repo.save_approval(approval)
        self.assertEqual(agent.execute_approved_transfers()[0].status, "TRANSFERRED")
        self.assertEqual(agent.request_claim("A1", "C-1", True).status, "CLAIM_PENDING")
        claim_approval = self.repo.list_approvals()[1]; claim_approval.status = "APPROVED"; self.repo.save_approval(claim_approval)
        self.assertEqual(agent.execute_approved_claims()[0].status, "CLAIM_PAID")

    def test_rejected_loan_can_be_reopened(self):
        self.repo.seed([LoanApplication("L3", "INCOME_VARIANCE", declared_income=100, verified_income=70, status=LoanStatus.AWAITING_APPROVAL.value)], [])
        agent = self.loan_agent()
        self.repo.create_approval(Approval("APR-0001", "LOAN_DEVIATION", "L3", "credit.manager", {"declared_income": 100, "verified_income": 70}))
        agent.reject_application("L3", "AI rejected due to missing evidence")
        self.assertEqual(self.repo.get_loan("L3").status, LoanStatus.REJECTED.value)
        agent.reopen_application("L3", "Customer resubmitted documents")
        reopened = self.repo.get_loan("L3")
        self.assertEqual(reopened.status, LoanStatus.AWAITING_CUSTOMER.value)
        self.assertIn("reopened", reopened.diagnosis.lower())

    def test_approved_loan_can_be_returned_to_main_journey(self):
        self.repo.seed([LoanApplication("L4", "INCOME_VARIANCE", declared_income=100, verified_income=70, status=LoanStatus.REOPENED.value)], [])
        agent = self.loan_agent()
        agent.approve_application("L4", "Approved by operations")
        self.assertEqual(self.repo.get_loan("L4").status, LoanStatus.READY_FOR_MAIN_JOURNEY.value)

    def test_operations_cannot_bypass_credit_manager_gate(self):
        self.repo.seed(
            [
                LoanApplication(
                    "L5",
                    "MISSING_DOCUMENT",
                    status=LoanStatus.REJECTED.value,
                    credit_score_decision="REJECTED_LOW_SCORE",
                )
            ],
            [],
        )
        with self.assertRaisesRegex(ValueError, "Credit Manager"):
            self.loan_agent().approve_application("L5", "Manual override")
        self.assertEqual(self.repo.get_loan("L5").status, LoanStatus.REJECTED.value)

    def test_automation_routes_loan_and_preserves_human_gate(self):
        self.repo.seed([LoanApplication("L2", "INCOME_VARIANCE", declared_income=100, verified_income=70)], [])
        loan = self.loan_agent()
        dormancy = self.dormancy_agent()
        result = OperationsAutomationAgent(self.repo, self.audit, loan, dormancy).run_cycle(date(2026, 7, 15))
        self.assertIn("Credit decision required for loan L2", result.pending_human_actions)
        self.assertEqual(self.repo.get_loan("L2").status, "AWAITING_APPROVAL")

    def test_document_model_identifies_missing_and_expired_documents(self):
        result = DocumentVerificationModel().verify("PERSONAL", {"PAN": "VALID", "AADHAAR": "EXPIRED"})
        self.assertIn("AADHAAR", result.invalid)
        self.assertIn("BANK_STATEMENT", result.missing)
        self.assertFalse(result.approved_for_document_stage)

    def test_document_ai_baseline_never_auto_approves(self):
        file_path = Path(self.temp.name) / "PAN.pdf"
        file_path.write_bytes(b"demo file")
        result = BaselineDocumentAIProvider().analyze("PAN", file_path)
        self.assertEqual(result.recommendation, "PENDING")


if __name__ == "__main__": unittest.main()
