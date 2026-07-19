from __future__ import annotations

"""Shared local-demo authentication for browser and API entrypoints."""

from dataclasses import dataclass
import hmac
from pathlib import Path

from .user_registry import UserRegistry


# These accounts exist only for local development. Credentials are never
# rendered by the application. Production must use the bank IdP, MFA, and RBAC.
LOCAL_DEMO_USERS = {
    "customer": ("customer123", "CUSTOMER", "Customer"),
    "loan.ops": ("ops123", "LOAN", "Loan Operations"),
    "credit.manager": ("credit123", "CREDIT", "Credit Manager"),
    "compliance.officer": ("compliance123", "COMPLIANCE", "Compliance Officer"),
    "admin": ("admin123", "ADMIN", "Administrator"),
}


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str
    display_name: str
    customer_id: str = ""


def authenticate_local_user(
    data_directory: str | Path,
    username: str,
    password: str,
    requested_role: str,
) -> AuthenticatedUser | None:
    user = LOCAL_DEMO_USERS.get(username)
    if user and hmac.compare_digest(password, user[0]) and user[1] == requested_role:
        return AuthenticatedUser(username, user[1], user[2], "CUST-1" if user[1] == "CUSTOMER" else "")
    registered = UserRegistry(Path(data_directory) / "users.json").authenticate(username, password, requested_role)
    if registered:
        return AuthenticatedUser(username, registered[0], registered[1], username if registered[0] == "CUSTOMER" else "")
    return None
