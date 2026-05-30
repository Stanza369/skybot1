import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet


# Store locations (relative to this backend folder)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BROKER_FILE = os.path.join(DATA_DIR, "broker_accounts.json")
KEY_FILE = os.path.join(DATA_DIR, ".broker_key")


def _ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_fernet() -> Fernet:
    _ensure_dirs()
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    return Fernet(key)


def _encrypt(s: str) -> str:
    if s is None:
        s = ""
    return _get_fernet().encrypt(s.encode("utf-8")).decode("utf-8")


def _decrypt(token: str) -> str:
    if token is None:
        return ""
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(BROKER_FILE):
        return {}
    with open(BROKER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_all(data: Dict[str, Any]) -> None:
    _ensure_dirs()
    tmp = BROKER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, BROKER_FILE)


@dataclass
class BrokerAccount:
    name: str
    account_type: str
    login: str
    server: str
    created_at: float


class BrokerStore:
    """Encrypted broker credentials vault (per-username)."""

    def __init__(self) -> None:
        # pure JSON persistence; no caching to keep it simple
        pass

    def add_account(
        self,
        *,
        username: str,
        account_name: str,
        account_type: str,
        login: str,
        password: str,
        server: str,
    ) -> Dict[str, Any]:
        if not username:
            return {"success": False, "error": "Missing username"}
        account_name = (account_name or "").strip()
        server = (server or "").strip()
        login = (login or "").strip()
        account_type = (account_type or "").strip().lower()

        if len(account_name) < 1:
            return {"success": False, "error": "Account name is required"}
        if account_type not in {"demo", "funded"}:
            return {"success": False, "error": "Invalid account type"}
        if len(login) < 1:
            return {"success": False, "error": "MT5 login is required"}
        if len(password) < 1:
            return {"success": False, "error": "MT5 password is required"}
        if len(server) < 1:
            return {"success": False, "error": "MT5 server is required"}

        all_data = _load_all()
        user_bucket = all_data.get(username) or {}
        accounts = user_bucket.get("accounts") or {}

        if account_name in accounts:
            return {"success": False, "error": "Account name already exists"}

        accounts[account_name] = {
            "account_type": account_type,
            "login": _encrypt(login),
            "password": _encrypt(password),
            "server": server,
            "created_at": time.time(),
            "last_used": None,
        }

        user_bucket["accounts"] = accounts
        all_data[username] = user_bucket
        _save_all(all_data)
        return {"success": True, "message": f"Account '{account_name}' saved securely"}

    def list_accounts(self, *, username: str) -> List[Dict[str, Any]]:
        if not username:
            return []
        all_data = _load_all()
        user_bucket = all_data.get(username) or {}
        accounts = user_bucket.get("accounts") or {}

        out: List[Dict[str, Any]] = []
        for name, data in accounts.items():
            out.append(
                {
                    "name": name,
                    "account_type": data.get("account_type"),
                    "login": _decrypt(data.get("login")),
                    "server": data.get("server"),
                    "created_at": data.get("created_at"),
                }
            )

        # stable ordering by created_at desc
        out.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
        return out

    def delete_account(self, *, username: str, account_name: str) -> Dict[str, Any]:
        if not username:
            return {"success": False, "error": "Missing username"}
        account_name = (account_name or "").strip()
        if len(account_name) < 1:
            return {"success": False, "error": "Account name is required"}

        all_data = _load_all()
        user_bucket = all_data.get(username) or {}
        accounts = user_bucket.get("accounts") or {}

        if account_name not in accounts:
            return {"success": False, "error": "Account not found"}

        del accounts[account_name]
        user_bucket["accounts"] = accounts
        all_data[username] = user_bucket
        _save_all(all_data)
        return {"success": True, "message": "Account deleted"}

    def get_account_for_connect(
        self, *, username: str, account_name: str
    ) -> Dict[str, Any]:
        if not username:
            return {"success": False, "error": "Missing username"}
        account_name = (account_name or "").strip()
        all_data = _load_all()
        user_bucket = all_data.get(username) or {}
        accounts = user_bucket.get("accounts") or {}

        if account_name not in accounts:
            return {"success": False, "error": "Account not found"}

        data = accounts[account_name]
        # decrypt only in backend right before connect
        login = _decrypt(data.get("login"))
        password = _decrypt(data.get("password"))
        server = data.get("server")

        # update last_used
        accounts[account_name] = {**data, "last_used": time.time()}
        user_bucket["accounts"] = accounts
        all_data[username] = user_bucket
        _save_all(all_data)

        return {
            "success": True,
            "account": {
                "account_type": data.get("account_type"),
                "login": login,
                "password": password,
                "server": server,
            },
        }

