import gc
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from banking_agents.api_app import create_app


class ApiAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.client = TestClient(create_app(self.root))

    def tearDown(self):
        self.client.close(); gc.collect(); self.temp.cleanup()

    @staticmethod
    def analysis_payload():
        return {"customer_id": "CUST-1", "header": {"customer_name": "Demo", "account_number_masked": "XXXX1234", "ifsc_code": "DEMO0001", "bank_name": "Demo Bank", "branch_name": "Main", "period_start": "2026-01-01", "period_end": "2026-02-28"}, "transactions": [{"transaction_date": "2026-01-01", "narration": "Salary NEFT", "credit": 50000, "running_balance": 50000, "reference_number": "R1"}, {"transaction_date": "2026-01-03", "narration": "Loan EMI NACH", "debit": 10000, "running_balance": 40000, "reference_number": "R2"}, {"transaction_date": "2026-02-01", "narration": "Salary NEFT", "credit": 50000, "running_balance": 90000, "reference_number": "R3"}], "evidence": {"consent_id": "CONSENT-1", "consented_at": "2026-01-01T00:00:00Z", "source": "ACCOUNT_AGGREGATOR", "itr_reported_income": 100000}}

    def test_openapi_contains_only_retained_products(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/v1/bank-statement-analyses", paths); self.assertIn("/api/v1/dormancy/cycles", paths)
        self.assertFalse(any(term in path for path in paths for term in ("credit-bureau", "chat", "loan-applications", "ai/models")))

    def test_upload_and_explainable_analysis(self):
        bad = self.client.post("/api/v1/financial-documents", data={"document_type": "BANK_STATEMENT"}, files=[("files", ("bad.txt", b"text", "text/plain"))])
        self.assertEqual(bad.status_code, 422)
        jpg = self.client.post("/api/v1/financial-documents", data={"document_type": "BANK_STATEMENT"}, files=[("files", ("statement.jpg", b"\xff\xd8\xff" + b"x" * 20, "image/jpeg"))])
        self.assertEqual(jpg.status_code, 201); self.assertEqual(jpg.json()["data"][0]["status"], "OCR_REVIEW_REQUIRED")
        created = self.client.post("/api/v1/bank-statement-analyses", json=self.analysis_payload())
        self.assertEqual(created.status_code, 201); data = created.json()["data"]
        self.assertEqual(data["metrics"]["average_monthly_income"], 50000); self.assertEqual(data["metrics"]["emi_to_income_ratio_percent"], 10); self.assertTrue(data["human_review_required"])
        self.assertEqual(self.client.get(f"/api/v1/bank-statement-analyses/{data['analysis_id']}").status_code, 200)

    def test_dormancy_maker_checker_and_export(self):
        created = self.client.post("/api/v1/dormancy/cycles", json={"account_id": "A1", "customer_id": "CUST-1", "jurisdiction": "IN-RBI-DEA", "balance": 1000, "last_customer_activity": "2016-01-01", "as_of_date": "2026-01-01"})
        self.assertEqual(created.status_code, 200); self.assertEqual(created.json()["data"]["status"], "TRANSFER_PENDING")
        approval = self.client.get("/api/v1/approvals").json()["data"][0]
        maker = self.client.post(f"/api/v1/approvals/{approval['approval_id']}/decision", json={"decision": "APPROVED", "note": "Maker reviewed package."})
        self.assertEqual(maker.json()["data"]["approval"]["status"], "MAKER_APPROVED")
        checker = self.client.post(f"/api/v1/approvals/{approval['approval_id']}/decision", json={"decision": "APPROVED", "note": "Independent checker."})
        self.assertEqual(checker.status_code, 200); self.assertEqual(checker.json()["data"]["transfers"][0]["status"], "TRANSFERRED")
        self.assertTrue(self.client.get("/api/v1/accounts/A1/regulatory-export").json()["data"]["simulation"])


if __name__ == "__main__": unittest.main()
