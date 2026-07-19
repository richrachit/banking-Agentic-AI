"""Local demo user registration with salted password hashes.

Production must delegate authentication to the bank's identity provider; this
file-backed registry is only for the local prototype.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re


class UserRegistry:
    reserved_local_usernames = {
        "customer",
        "loan.ops",
        "credit.manager",
        "compliance.officer",
        "admin",
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("{}", encoding="utf-8")

    def register(self, username: str, password: str, display_name: str, email: str, role: str) -> str:
        username = username.strip()
        display_name = display_name.strip()
        email = email.strip()
        role = role.strip().upper()
        users = json.loads(self.path.read_text(encoding="utf-8"))
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", username):
            raise ValueError("Username must be 3-64 letters, numbers, dots, underscores, or hyphens.")
        if username.lower() in self.reserved_local_usernames:
            raise ValueError("Username is reserved by a local demo account.")
        if username in users:
            raise ValueError("Username is already registered.")
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters.")
        if len(password) > 256:
            raise ValueError("Password must not exceed 256 characters.")
        if not display_name or len(display_name) > 100:
            raise ValueError("Display name must contain 1-100 characters.")
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Enter a valid email address.")
        if role not in {"CUSTOMER", "LOAN", "CREDIT", "COMPLIANCE"}:
            raise ValueError("Unsupported signup role.")
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        users[username] = {"display_name": display_name, "email": email, "role": role, "status": "ACTIVE" if role == "CUSTOMER" else "PENDING_APPROVAL", "salt": base64.b64encode(salt).decode(), "password_hash": base64.b64encode(digest).decode()}
        self.path.write_text(json.dumps(users, indent=2, sort_keys=True), encoding="utf-8")
        return users[username]["status"]

    def authenticate(self, username: str, password: str, role: str) -> tuple[str, str] | None:
        users = json.loads(self.path.read_text(encoding="utf-8"))
        user = users.get(username)
        if not user or user["role"] != role or user["status"] != "ACTIVE":
            return None
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(user["salt"]), 310_000)
        if not hmac.compare_digest(digest, base64.b64decode(user["password_hash"])):
            return None
        return user["role"], user["display_name"]
