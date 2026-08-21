import unittest
from banking_agents.web_app import PAGE


class WebScopeTests(unittest.TestCase):
    def test_ui_contains_only_retained_products(self):
        self.assertIn("Bank Statement & AA Verification", PAGE); self.assertIn("Dormant Account Lifecycle", PAGE)
        self.assertNotIn("Credit Bureau", PAGE); self.assertNotIn("Support Chatbot", PAGE)


if __name__ == "__main__": unittest.main()
