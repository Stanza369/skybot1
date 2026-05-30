from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from auth import get_password_hash, verify_password


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def _ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_all() -> Dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all(data: Dict[str, Any]) -> None:
    _ensure_dirs()
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, USERS_FILE)


@dataclass
class UserRecord:
    username: str
    email: str
    role: str = "user"  # "admin" or "user"
    status: str = "pending"  # "pending" | "approved" | "rejected"
    disabled: bool = False
    password_hash: str = ""
    created_at: float = 0.0

    @classmethod
    def from_dict(cls, username: str, d: Dict[str, Any]) -> "UserRecord":
        return cls(
            username=username,
            email=d.get("email", ""),
            role=d.get("role", "user"),
            status=d.get("status", "pending"),
            disabled=bool(d.get("disabled", False)),
            password_hash=d.get("password_hash", ""),
            created_at=float(d.get("created_at", 0.0) or 0.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "disabled": self.disabled,
            "password_hash": self.password_hash,
            "created_at": self.created_at,
        }


class UserStore:
    """Persistent user store for the dashboard auth + admin approval system."""

    def __init__(self) -> None:
        # Ensure data file exists and default admin is created if configured.
        self._bootstrap_admin_if_missing()

    def _bootstrap_admin_if_missing(self) -> None:
        data = _load_all()

        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        if admin_username in data:
            return

        data[admin_username] = UserRecord(
            username=admin_username,
            email=os.getenv("ADMIN_EMAIL", "admin@trading.com"),
            role="admin",
            status="approved",
            disabled=False,
            password_hash=get_password_hash(admin_password),
            created_at=time.time(),
        ).to_dict()

        _save_all(data)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        if not username:
            return None
        data = _load_all()
        return data.get(username)

    def get_user_by_login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user(username)
        if not user:
            return None
        if user.get("disabled"):
            return None
        if user.get("role") != "admin" and user.get("status") != "approved":
            return None

        if not verify_password(password, user.get("password_hash", "")):
            return None
        return user

    def create_user(self, *, username: str, email: str, password: str) -> Dict[str, Any]:
        username = (username or "").strip()
        email = (email or "").strip()
        if len(username) < 3:
            return {"success": False, "error": "Username min 3 characters"}
        if not email or "@" not in email:
            return {"success": False, "error": "Valid email required"}
        if not password or len(password) < 6:
            return {"success": False, "error": "Password min 6 characters"}

        data = _load_all()
        if username in data:
            return {"success": False, "error": "Username already exists"}

        rec = UserRecord(
            username=username,
            email=email,
            role="user",
            status="pending",
            disabled=False,
            password_hash=get_password_hash(password),
            created_at=time.time(),
        )
        data[username] = rec.to_dict()
        _save_all(data)
        return {"success": True}

    def list_pending(self) -> Dict[str, Dict[str, Any]]:
        data = _load_all()
        return {u: rec for u, rec in data.items() if rec.get("role") != "admin" and rec.get("status") == "pending"}

    def list_users(self) -> Dict[str, Dict[str, Any]]:
        return _load_all()

    def approve(self, username: str) -> Dict[str, Any]:
        username = (username or "").strip()
        data = _load_all()
        if username not in data:
            return {"success": False, "error": "User not found"}
        if data[username].get("role") == "admin":
            return {"success": False, "error": "Cannot approve admin"}

        data[username]["status"] = "approved"
        _save_all(data)
        return {"success": True}

    def reject(self, username: str) -> Dict[str, Any]:
        username = (username or "").strip()
        data = _load_all()
        if username not in data:
            return {"success": False, "error": "User not found"}
        if data[username].get("role") == "admin":
            return {"success": False, "error": "Cannot reject admin"}

        data[username]["status"] = "rejected"
        _save_all(data)
        return {"success": True}

