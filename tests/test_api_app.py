import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from banking_agents.api_app import create_app
from banking_agents.credit_bureau_agent import LocalCreditBureauDatabase


class ApiAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        bureau = LocalCreditBureauDatabase(self.root / "credit_bureau.sqlite3")
        bureau.seed_fixture("DEMOA0001A", 790, "API-HIGH")
        bureau.seed_fixture("DEMOC0003C", 580, "API-LOW")
        self.client = TestClient(create_app(self.root))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def login(self, username="customer", password="customer123", user_type="CUSTOMER"):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password, "user_type": user_type},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['data']['accessToken']}"}

    @staticmethod
    def loan_payload(pan):
        return {
            "applicant_name": "API Customer",
            "date_of_birth": "1990-01-01",
            "email": "api@example.test",
            "phone": "9999999999",
            "residential_address": "Test address",
            "loan_product": "PERSONAL",
            "requested_amount": 250000,
            "tenure_months": 24,
            "loan_purpose": "Education",
            "employment_type": "SALARIED",
            "employer_name": "Example",
            "monthly_income": 50000,
            "pan_for_bureau_lookup": pan,
            "credit_bureau_consent": True,
            "uploaded_document_types": ["PAN"],
        }

    def test_openapi_and_health_are_available(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/api/v1/loan-applications", schema.json()["paths"])

    def test_high_score_continues_and_low_score_rejects(self):
        headers = self.login()
        high = self.client.post("/api/v1/loan-applications", json=self.loan_payload("DEMOA0001A"), headers=headers)
        self.assertEqual(high.status_code, 201)
        self.assertEqual(high.json()["data"]["credit_score_decision"], "PROCEED_TO_WORKFLOW")
        self.assertEqual(high.json()["data"]["status"], "AWAITING_CUSTOMER")
        low = self.client.post("/api/v1/loan-applications", json=self.loan_payload("DEMOC0003C"), headers=headers)
        self.assertEqual(low.status_code, 201)
        self.assertEqual(low.json()["data"]["status"], "REJECTED")
        loans = self.client.get("/api/v1/loan-applications", headers=headers).json()["data"]
        self.assertEqual(len(loans), 2)

    def test_loan_submission_requires_consent(self):
        headers = self.login()
        payload = self.loan_payload("DEMOA0001A")
        payload["credit_bureau_consent"] = False
        response = self.client.post("/api/v1/loan-applications", json=payload, headers=headers)
        self.assertEqual(response.status_code, 422)

    def test_model_registry_is_admin_only(self):
        customer_headers = self.login()
        self.assertEqual(self.client.get("/api/v1/ai/models", headers=customer_headers).status_code, 403)
        admin_headers = self.login("admin", "admin123", "ADMIN")
        response = self.client.get("/api/v1/ai/models", headers=admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["data"]["components"]), 10)


if __name__ == "__main__":
    unittest.main()
