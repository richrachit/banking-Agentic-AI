import unittest

from banking_agents.kyc_ai import IndiaKycAIAgent, KycInput, KycStatus


class IndiaKycAIAgentTests(unittest.TestCase):
    def test_invalid_pan_is_rejected(self):
        decision = IndiaKycAIAgent().assess(KycInput(consent_recorded=True, pan="INVALID"))
        self.assertEqual(decision.status, KycStatus.REJECTED)

    def test_external_checks_are_required_before_verified(self):
        decision = IndiaKycAIAgent().assess(KycInput(consent_recorded=True, pan="ABCDE1234F"))
        self.assertEqual(decision.status, KycStatus.PENDING_EXTERNAL_VERIFICATION)
        self.assertTrue(decision.required_actions)


if __name__ == "__main__":
    unittest.main()
