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
from banking_agents.models import Account, LoanApplication
from banking_agents.policy import PolicyConfig
from banking_agents.repository import LocalRepository


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.repo = LocalRepository(root / "state.json"); self.audit = AuditLog(root / "audit.jsonl"); self.policy = PolicyConfig()

    def tearDown(self): self.temp.cleanup()

    def test_income_deviation_needs_then_applies_approval(self):
        self.repo.seed([LoanApplication("L1", "INCOME_VARIANCE", declared_income=100, verified_income=70)], [])
        agent = LoanExceptionAgent(self.repo, self.audit, self.policy)
        self.assertEqual(agent.run("L1").status, "AWAITING_APPROVAL")
        approval = self.repo.list_approvals()[0]; approval.status = "APPROVED"; self.repo.save_approval(approval)
        self.assertEqual(agent.apply_approved_deviation("L1").status, "READY_FOR_MAIN_JOURNEY")

    def test_dormant_account_requires_approval_before_transfer(self):
        self.repo.seed([], [Account("A1", "C1", "IN-RBI-DEA", 90, "2010-01-01")])
        agent = DormancyAgent(self.repo, self.audit, self.policy); agent.run(date(2026, 7, 15))
        self.assertEqual(self.repo.get_account("A1").status, "TRANSFER_PENDING")
        approval = self.repo.list_approvals()[0]; approval.status = "APPROVED"; self.repo.save_approval(approval)
        self.assertEqual(agent.execute_approved_transfers()[0].status, "TRANSFERRED")
        self.assertEqual(agent.request_claim("A1", "C-1", True).status, "CLAIM_PENDING")
        claim_approval = self.repo.list_approvals()[1]; claim_approval.status = "APPROVED"; self.repo.save_approval(claim_approval)
        self.assertEqual(agent.execute_approved_claims()[0].status, "CLAIM_PAID")

    def test_automation_routes_loan_and_preserves_human_gate(self):
        self.repo.seed([LoanApplication("L2", "INCOME_VARIANCE", declared_income=100, verified_income=70)], [])
        loan = LoanExceptionAgent(self.repo, self.audit, self.policy)
        dormancy = DormancyAgent(self.repo, self.audit, self.policy)
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
