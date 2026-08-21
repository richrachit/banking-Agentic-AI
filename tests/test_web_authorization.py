import unittest
from banking_agents.web_app import PAGE


class WebScopeTests(unittest.TestCase):
    def test_single_home_connects_all_three_features(self):
        self.assertIn("Feature Home", PAGE)
        self.assertIn("Open Bank Statement Analysis", PAGE)
        self.assertIn("Open Income Verification", PAGE)
        self.assertIn("Open Dormancy Lifecycle", PAGE)
        self.assertIn('id="statements"', PAGE); self.assertIn('id="verification"', PAGE); self.assertIn('id="dormancy"', PAGE)
        self.assertNotIn("Credit Bureau", PAGE); self.assertNotIn("Support Chatbot", PAGE)


if __name__ == "__main__": unittest.main()
