"""Local credentials roster for soft.awwthat.com test accounts."""
from __future__ import annotations

import json
from typing import Any

from app.config import DATA_DIR, USERS_FILE


def load_roster() -> list[dict[str, str]]:
    if not USERS_FILE.exists():
        return []
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    users = data.get("users") or []
    out: list[dict[str, str]] = []
    for user in users:
        username = str(user.get("username", "")).strip()
        password = str(user.get("password", "")).strip()
        if not username:
            continue
        out.append(
            {
                "username": username,
                "password": password,
                "label": str(user.get("label") or username),
            }
        )
    return out


def save_roster(users: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for user in users:
        username = str(user.get("username", "")).strip()
        if not username:
            continue
        cleaned.append(
            {
                "username": username,
                "password": str(user.get("password", "")),
                "label": str(user.get("label") or username),
            }
        )
    USERS_FILE.write_text(json.dumps({"users": cleaned}, indent=2) + "\n", encoding="utf-8")


def upsert_user(username: str, password: str, label: str | None = None) -> None:
    username = username.strip()
    password = password.strip()
    label = (label or username).strip()
    users = load_roster()
    for user in users:
        if user["username"].lower() == username.lower():
            user["username"] = username
            user["password"] = password
            user["label"] = label
            save_roster(users)
            return
    users.append({"username": username, "password": password, "label": label})
    save_roster(users)
