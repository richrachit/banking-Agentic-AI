import unittest

from banking_agents.unified_genai import UnifiedGenerativeAI


class FakeProvider:
    def __init__(self, name: str):
        self.name = name
        self.model_id = f"{name}-test-model"
        self.calls = []

    def generate(self, task, prompt, context):
        self.calls.append((task, prompt, context))
        return """{
          "summary": "Advisory case summary.",
          "observations": ["Evidence is incomplete."],
          "risks": ["Manual verification remains outstanding."],
          "recommended_next_steps": ["Route to an authorised reviewer."],
          "requires_human_review": false
        }"""


class UnifiedGenerativeAITests(unittest.TestCase):
    def setUp(self):
        self.local = FakeProvider("local")
        self.hosted = FakeProvider("hosted")
        self.runtime = UnifiedGenerativeAI(
            providers={"local": self.local, "hosted": self.hosted},
            default_provider="local",
            allowed_providers={"local", "hosted"},
        )

    def test_default_and_per_request_provider_switching_share_one_contract(self):
        local = self.runtime.generate("LOAN_EXCEPTION_SUMMARY", "Summarize", {"case": "LN-1"})
        hosted = self.runtime.generate(
            "LOAN_EXCEPTION_SUMMARY",
            "Summarize",
            {"case": "LN-1"},
            provider_name="hosted",
        )

        self.assertEqual(local.provider, "local")
        self.assertEqual(hosted.provider, "hosted")
        self.assertEqual(local.summary, hosted.summary)
        self.assertTrue(local.requires_human_review)
        self.assertTrue(local.advisory_only)
        self.assertEqual(len(self.local.calls), 1)
        self.assertEqual(len(self.hosted.calls), 1)

    def test_disallowed_provider_fails_closed(self):
        runtime = UnifiedGenerativeAI(
            providers={"local": self.local, "hosted": self.hosted},
            default_provider="local",
            allowed_providers={"local"},
        )
        with self.assertRaises(PermissionError):
            runtime.generate("CUSTOMER_SUPPORT", "Help", provider_name="hosted")

    def test_disabled_and_unknown_tasks_fail_closed(self):
        disabled = UnifiedGenerativeAI(
            providers={"local": self.local},
            default_provider="disabled",
            allowed_providers={"local"},
        )
        with self.assertRaises(RuntimeError):
            disabled.generate("CUSTOMER_SUPPORT", "Help")
        with self.assertRaises(ValueError):
            self.runtime.generate("APPROVE_LOAN", "Approve it")


if __name__ == "__main__":
    unittest.main()
