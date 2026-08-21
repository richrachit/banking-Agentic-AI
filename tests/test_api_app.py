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

    def login(self, username="customer", password="customer123", role="CUSTOMER"):
        result = self.client.post("/api/v1/auth/login", json={"username": username, "password": password, "user_type": role})
        self.assertEqual(result.status_code, 200)
        return {"Authorization": "Bearer " + result.json()["data"]["accessToken"]}

    @staticmethod
    def analysis_payload():
        return {"customer_id": "CUST-1", "header": {"customer_name": "Demo", "account_number_masked": "XXXX1234", "ifsc_code": "DEMO0001", "bank_name": "Demo Bank", "branch_name": "Main", "period_start": "2026-01-01", "period_end": "2026-02-28"}, "transactions": [{"transaction_date": "2026-01-01", "narration": "Salary NEFT", "credit": 50000, "running_balance": 50000, "reference_number": "R1"}, {"transaction_date": "2026-01-03", "narration": "Loan EMI NACH", "debit": 10000, "running_balance": 40000, "reference_number": "R2"}, {"transaction_date": "2026-02-01", "narration": "Salary NEFT", "credit": 50000, "running_balance": 90000, "reference_number": "R3"}], "evidence": {"consent_id": "CONSENT-1", "consented_at": "2026-01-01T00:00:00Z", "source": "ACCOUNT_AGGREGATOR", "itr_reported_income": 100000}}

    def test_openapi_contains_only_retained_products(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/v1/bank-statement-analyses", paths); self.assertIn("/api/v1/dormancy/cycles", paths)
        self.assertFalse(any(term in path for path in paths for term in ("credit-bureau", "chat", "loan-applications", "ai/models")))

    def test_upload_and_explainable_analysis(self):
        customer = self.login()
        bad = self.client.post("/api/v1/financial-documents", headers=customer, data={"document_type": "BANK_STATEMENT"}, files=[("files", ("bad.txt", b"text", "text/plain"))])
        self.assertEqual(bad.status_code, 422)
        jpg = self.client.post("/api/v1/financial-documents", headers=customer, data={"document_type": "BANK_STATEMENT"}, files=[("files", ("statement.jpg", b"\xff\xd8\xff" + b"x" * 20, "image/jpeg"))])
        self.assertEqual(jpg.status_code, 201); self.assertEqual(jpg.json()["data"][0]["status"], "OCR_REVIEW_REQUIRED")
        created = self.client.post("/api/v1/bank-statement-analyses", headers=customer, json=self.analysis_payload())
        self.assertEqual(created.status_code, 201); data = created.json()["data"]
        self.assertEqual(data["metrics"]["average_monthly_income"], 50000); self.assertEqual(data["metrics"]["emi_to_income_ratio_percent"], 10); self.assertTrue(data["human_review_required"])
        underwriter = self.login("underwriter", "underwriter123", "UNDERWRITER")
        self.assertEqual(self.client.get(f"/api/v1/bank-statement-analyses/{data['analysis_id']}", headers=underwriter).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/bank-statement-analyses/{data['analysis_id']}", headers=customer).status_code, 403)

    def test_dormancy_maker_checker_and_export(self):
        compliance = self.login("compliance.officer", "compliance123", "COMPLIANCE")
        created = self.client.post("/api/v1/dormancy/cycles", headers=compliance, json={"account_id": "A1", "customer_id": "CUST-1", "jurisdiction": "IN-RBI-DEA", "balance": 1000, "last_customer_activity": "2016-01-01", "as_of_date": "2026-01-01"})
        self.assertEqual(created.status_code, 200); self.assertEqual(created.json()["data"]["status"], "TRANSFER_PENDING")
        approval = self.client.get("/api/v1/approvals", headers=compliance).json()["data"][0]
        maker = self.client.post(f"/api/v1/approvals/{approval['approval_id']}/decision", headers=compliance, json={"decision": "APPROVED", "note": "Maker reviewed package."})
        self.assertEqual(maker.json()["data"]["approval"]["status"], "MAKER_APPROVED")
        same = self.client.post(f"/api/v1/approvals/{approval['approval_id']}/decision", headers=compliance, json={"decision": "APPROVED", "note": "Same actor check."})
        self.assertEqual(same.status_code, 403)
        admin = self.login("admin", "admin123", "ADMIN")
        checker = self.client.post(f"/api/v1/approvals/{approval['approval_id']}/decision", headers=admin, json={"decision": "APPROVED", "note": "Independent checker."})
        self.assertEqual(checker.status_code, 200); self.assertEqual(checker.json()["data"]["transfers"][0]["status"], "TRANSFERRED")
        self.assertTrue(self.client.get("/api/v1/accounts/A1/regulatory-export", headers=admin).json()["data"]["simulation"])


if __name__ == "__main__": unittest.main()
