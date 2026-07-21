import gc
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from banking_agents.api_app import create_app
from banking_agents.credit_bureau_agent import LocalCreditBureauDatabase
from banking_agents.models import Account, DormancyStatus
from banking_agents.repository import LocalRepository


class ApiAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        bureau = LocalCreditBureauDatabase(self.root / "credit_bureau.sqlite3")
        bureau.seed_fixture("DEMOA0001A", 790, "API-HIGH")
        bureau.seed_fixture("DEMOB0002B", 710, "API-REVIEW")
        bureau.seed_fixture("DEMOC0003C", 580, "API-LOW")
        bureau.seed_fixture("DEMOD0004D", None, "API-NO-HISTORY")
        self.client = TestClient(create_app(self.root))

    def tearDown(self):
        self.client.close()
        gc.collect()
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

    def test_chat_endpoint_requires_auth_is_read_only_and_does_not_audit_message_text(self):
        self.assertEqual(self.client.post("/api/v1/chat/messages", json={"message": "hello"}).status_code, 401)
        headers = self.login()
        secret_message = "PRIVATE-CHAT-TEXT-DO-NOT-PERSIST what is my loan status?"
        response = self.client.post(
            "/api/v1/chat/messages",
            json={"message": secret_message},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["intent"], "LOAN_STATUS")
        self.assertTrue(data["read_only"])
        self.assertIn("authority_boundary", data)

        audit = (self.root / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn("chat.assistant_responded", audit)
        self.assertNotIn("PRIVATE-CHAT-TEXT-DO-NOT-PERSIST", audit)

    def test_admin_agent_settings_are_role_restricted_and_fail_closed(self):
        customer_headers = self.login()
        self.assertEqual(self.client.get("/api/v1/ai/agents", headers=customer_headers).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/ai/agents/banking_support_chatbot/settings",
                json={"enabled": False},
                headers=customer_headers,
            ).status_code,
            403,
        )

        admin_headers = self.login("admin", "admin123", "ADMIN")
        listing = self.client.get("/api/v1/ai/agents", headers=admin_headers)
        self.assertEqual(listing.status_code, 200)
        settings = {item["model_key"]: item for item in listing.json()["data"]["agents"]}
        self.assertIn("banking_support_chatbot", settings)
        self.assertTrue(settings["banking_support_chatbot"]["fail_closed_when_disabled"])

        disabled = self.client.post(
            "/api/v1/ai/agents/banking_support_chatbot/settings",
            json={"enabled": False},
            headers=admin_headers,
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()["data"]["enabled"])
        unavailable = self.client.post(
            "/api/v1/chat/messages",
            json={"message": "What can you help me with?"},
            headers=customer_headers,
        )
        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("disabled", unavailable.json()["detail"].lower())

        enabled = self.client.post(
            "/api/v1/ai/agents/banking_support_chatbot/settings",
            json={"enabled": True},
            headers=admin_headers,
        )
        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(enabled.json()["data"]["enabled"])
        self.assertEqual(
            self.client.post(
                "/api/v1/chat/messages",
                json={"message": "What can you help me with?"},
                headers=customer_headers,
            ).status_code,
            200,
        )

        self.client.post(
            "/api/v1/ai/agents/credit_bureau_decision_agent/settings",
            json={"enabled": False},
            headers=admin_headers,
        )
        blocked_loan = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("DEMOA0001A"),
            headers=customer_headers,
        )
        self.assertEqual(blocked_loan.status_code, 503)
        self.client.post(
            "/api/v1/ai/agents/credit_bureau_decision_agent/settings",
            json={"enabled": True},
            headers=admin_headers,
        )

    def test_intermediate_score_approval_resumes_document_workflow_once(self):
        customer_headers = self.login()
        created = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("DEMOB0002B"),
            headers=customer_headers,
        )
        self.assertEqual(created.status_code, 201)
        loan = created.json()["data"]
        self.assertEqual(loan["status"], "AWAITING_APPROVAL")
        credit_headers = self.login("credit.manager", "credit123", "CREDIT")
        approvals = self.client.get("/api/v1/approvals", headers=credit_headers).json()["data"]
        approval = next(item for item in approvals if item["entity_id"] == loan["application_id"])
        decision = self.client.post(
            f"/api/v1/approvals/{approval['approval_id']}/decision",
            json={"decision": "APPROVED", "note": "Income and bureau file reviewed."},
            headers=credit_headers,
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["data"]["updatedEntity"]["status"], "AWAITING_CUSTOMER")
        detail = self.client.get(
            f"/api/v1/loan-applications/{loan['application_id']}",
            headers=customer_headers,
        ).json()["data"]["application"]
        self.assertEqual(detail["credit_score"], 710)
        self.assertEqual(detail["credit_score_decision"], "HUMAN_REVIEW_APPROVED")
        duplicate = self.client.post(
            f"/api/v1/approvals/{approval['approval_id']}/decision",
            json={"decision": "APPROVED", "note": "Duplicate"},
            headers=credit_headers,
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_low_score_customer_can_request_governed_reconsideration(self):
        customer_headers = self.login()
        created = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("DEMOC0003C"),
            headers=customer_headers,
        ).json()["data"]
        review = self.client.post(
            f"/api/v1/loan-applications/{created['application_id']}/credit-review-requests",
            json={"reason": "The bureau entry is disputed and has been corrected.", "bureau_dispute_reference": "DISPUTE-1"},
            headers=customer_headers,
        )
        self.assertEqual(review.status_code, 201)
        unchanged = self.client.get(
            f"/api/v1/loan-applications/{created['application_id']}",
            headers=customer_headers,
        ).json()["data"]["application"]
        self.assertEqual(unchanged["status"], "REJECTED")
        self.assertEqual(unchanged["credit_score"], 580)

        credit_headers = self.login("credit.manager", "credit123", "CREDIT")
        approval_id = review.json()["data"]["approval_id"]
        missing_note = self.client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "REJECTED", "note": ""},
            headers=credit_headers,
        )
        self.assertEqual(missing_note.status_code, 422)
        approved = self.client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "APPROVED", "note": "Correction evidence verified."},
            headers=credit_headers,
        )
        self.assertEqual(approved.status_code, 200)
        updated = approved.json()["data"]["updatedEntity"]
        self.assertEqual(updated["status"], "AWAITING_CUSTOMER")
        self.assertEqual(updated["credit_score"], 580)
        self.assertEqual(updated["credit_score_decision"], "LOW_SCORE_RECONSIDERATION_APPROVED")

    def test_customer_ownership_blocks_other_customer_detail_upload_and_review(self):
        owner_headers = self.login()
        created = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("DEMOC0003C"),
            headers=owner_headers,
        ).json()["data"]
        signup = self.client.post(
            "/api/v1/auth/signup",
            json={
                "username": "other.customer",
                "password": "other-password-123",
                "display_name": "Other Customer",
                "email": "other@example.test",
                "user_type": "CUSTOMER",
            },
        )
        self.assertEqual(signup.status_code, 201)
        other_headers = self.login("other.customer", "other-password-123", "CUSTOMER")
        application_id = created["application_id"]
        self.assertEqual(
            self.client.get(f"/api/v1/loan-applications/{application_id}", headers=other_headers).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/loan-applications/{application_id}/documents",
                data={"document_type": "PAN"},
                files={"file": ("pan.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
                headers=other_headers,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/loan-applications/{application_id}/credit-review-requests",
                json={"reason": "I should not be able to review another customer loan."},
                headers=other_headers,
            ).status_code,
            404,
        )

    def test_document_upload_checks_type_signature_and_does_not_store_filename(self):
        headers = self.login()
        created = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("DEMOA0001A"),
            headers=headers,
        ).json()["data"]
        application_id = created["application_id"]
        invalid = self.client.post(
            f"/api/v1/loan-applications/{application_id}/documents",
            data={"document_type": "AADHAAR"},
            files={"file": ("aadhaar.pdf", b"not really a pdf", "application/pdf")},
            headers=headers,
        )
        self.assertEqual(invalid.status_code, 422)
        valid = self.client.post(
            f"/api/v1/loan-applications/{application_id}/documents",
            data={"document_type": "AADHAAR"},
            files={"file": ("my-sensitive-name.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            headers=headers,
        )
        self.assertEqual(valid.status_code, 201)
        upload_names = [item.name for item in (self.root / "uploads" / application_id).iterdir()]
        self.assertEqual(upload_names, ["AADHAAR.pdf"])

    def test_consent_evidence_is_persisted_without_raw_pan(self):
        headers = self.login()
        response = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("DEMOA0001A"),
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)
        application = response.json()["data"]
        self.assertEqual(application["credit_bureau_consent_version"], "CREDIT_BUREAU_CONSENT_V1")
        self.assertTrue(application["credit_bureau_consent_recorded_at"])
        with closing(sqlite3.connect(self.root / "credit_bureau.sqlite3")) as connection:
            row = connection.execute(
                "SELECT consent_recorded, consent_version, consent_purpose FROM credit_score_check"
            ).fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "CREDIT_BUREAU_CONSENT_V1")
        self.assertEqual(row[2], "LOAN_ELIGIBILITY_AND_CREDIT_RISK_ASSESSMENT")
        self.assertNotIn(b"DEMOA0001A", (self.root / "credit_bureau.sqlite3").read_bytes())

    def test_unavailable_fixture_routes_to_review_and_validation_does_not_echo_pan(self):
        headers = self.login()
        unavailable = self.client.post(
            "/api/v1/loan-applications",
            json=self.loan_payload("ABCDE1234F"),
            headers=headers,
        )
        self.assertEqual(unavailable.status_code, 201)
        self.assertEqual(unavailable.json()["data"]["credit_score_decision"], "HUMAN_REVIEW_BUREAU_UNAVAILABLE")
        payload = self.loan_payload("THIS_IS_NOT_A_PAN")
        invalid = self.client.post("/api/v1/loan-applications", json=payload, headers=headers)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.headers["content-type"], "application/problem+json")
        self.assertNotIn("THIS_IS_NOT_A_PAN", invalid.text)

    def test_dev_cors_is_exact_and_sensitive_responses_are_not_cached(self):
        allowed = self.client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://localhost:8000")
        denied = self.client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertIsNone(denied.headers.get("access-control-allow-origin"))
        self.assertEqual(self.client.get("/api/v1/health").headers.get("cache-control"), "no-store")

    def test_dormant_account_reactivation_uses_authenticated_customer(self):
        repository = LocalRepository(self.root / "state.json")
        repository.save_account(
            Account(
                "ACC-CUST-1",
                "CUST-1",
                "IN-RBI-DEA",
                1000,
                "2010-01-01",
                status=DormancyStatus.DORMANT.value,
            )
        )
        customer_headers = self.login()
        request = self.client.post(
            "/api/v1/accounts/ACC-CUST-1/reactivation-requests",
            json={"kyc_confirmed": True},
            headers=customer_headers,
        )
        self.assertEqual(request.status_code, 201)
        compliance_headers = self.login("compliance.officer", "compliance123", "COMPLIANCE")
        decision = self.client.post(
            f"/api/v1/approvals/{request.json()['data']['approval_id']}/decision",
            json={"decision": "APPROVED", "note": "KYC was verified."},
            headers=compliance_headers,
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["data"]["updatedEntity"]["status"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()
