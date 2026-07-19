import tempfile
import unittest
from pathlib import Path

from banking_agents.user_registry import UserRegistry


class UserRegistryTests(unittest.TestCase):
    def test_customer_signup_and_authentication(self):
        with tempfile.TemporaryDirectory() as root:
            registry = UserRegistry(Path(root) / "users.json")
            self.assertEqual(registry.register("new.customer", "strong-password", "New Customer", "new@example.com", "CUSTOMER"), "ACTIVE")
            self.assertEqual(registry.authenticate("new.customer", "strong-password", "CUSTOMER"), ("CUSTOMER", "New Customer"))


if __name__ == "__main__":
    unittest.main()
