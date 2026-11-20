"""JSON API for the Laneora Soft server.

Any HTTP client that can reach the server can call these routes. Send the
dashboard username and password to POST /api/v1/session, then pass the returned
token as Authorization: Bearer <token> (or X-API-Key).
"""
from __future__ import annotations

import hmac
import json
import re
from typing import Any
from urllib.parse import unquote, urlparse

from app import __version__
from app.services import service_catalog
from server.soft_admin_lib import (
    create_account,
    dashboard_login,
    delete_account,
    ensure_api_token,
    list_accounts,
    load_config,
    rotate_api_token,
    update_account,
)
from server.subscriptions import account_status, plan_catalog

_USER_PATH = re.compile(r"^/api/v1/users/([^/]+)$")

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Max-Age": "86400",
}

_ROUTES: list[dict[str, Any]] = [
    {"method": "GET", "path": "/api/v1", "auth": False, "description": "This index."},
    {"method": "GET", "path": "/api/v1/health", "auth": False, "description": "The server is up."},
    {
        "method": "POST",
        "path": "/api/v1/session",
        "auth": False,
        "description": "Exchange the dashboard username and password for a bearer token.",
    },
    {"method": "GET", "path": "/api/v1/catalog", "auth": True, "description": "Plans and services."},
    {"method": "GET", "path": "/api/v1/users", "auth": True, "description": "List accounts."},
    {"method": "POST", "path": "/api/v1/users", "auth": True, "description": "Create an account."},
    {"method": "GET", "path": "/api/v1/users/{username}", "auth": True, "description": "One account."},
    {
        "method": "PATCH",
        "path": "/api/v1/users/{username}",
        "auth": True,
        "description": "Change the password, plan, active flag, or services.",
    },
    {"method": "DELETE", "path": "/api/v1/users/{username}", "auth": True, "description": "Delete an account."},
    {
        "method": "POST",
        "path": "/api/v1/token/rotate",
        "auth": True,
        "description": "Replace the bearer token. The previous token stops working.",
    },
]


def _eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _path(handler: Any) -> str:
    path = urlparse(handler.path).path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _read_json(handler: Any) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length > 64_000:
        raise ValueError("Request is too large.")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Send JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Send a JSON object.")
    return data


def _send(handler: Any, code: int, body: bytes, content_type: str) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in _CORS.items():
        handler.send_header(key, value)
    handler.end_headers()
    if getattr(handler, "command", "") != "HEAD":
        handler.wfile.write(body)


def _send_json(handler: Any, code: int, payload: dict[str, Any]) -> None:
    _send(handler, code, _json_bytes(payload), "application/json; charset=utf-8")


def _presented_token(handler: Any) -> str:
    auth = handler.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (handler.headers.get("X-API-Key") or "").strip()


def _authorized(handler: Any) -> bool:
    presented = _presented_token(handler)
    expected = ensure_api_token()
    if not presented or not expected:
        return False
    return _eq(presented, expected)


def _require_auth(handler: Any) -> bool:
    if _authorized(handler):
        return True
    _send_json(handler, 401, {"ok": False, "error": "Send Authorization: Bearer <token>."})
    return False


def _summary(users: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(users), "active": 0, "expired": 0, "disabled": 0, "unset": 0}
    for user in users:
        status = str(user.get("status") or "")
        if status in counts:
            counts[status] += 1
    return counts


def _find_user(username: str) -> dict[str, Any] | None:
    wanted = username.strip().lower()
    for user in list_accounts():
        if str(user.get("username") or "").lower() == wanted:
            return user
    return None


def _username_from_path(path: str) -> str | None:
    match = _USER_PATH.match(path)
    if match is None:
        return None
    return unquote(match.group(1)).strip()


def _index() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "laneora",
        "version": __version__,
        "auth": "Authorization: Bearer <token>",
        "session": {
            "method": "POST",
            "path": "/api/v1/session",
            "body": {"username": "dashboard username", "password": "dashboard password"},
        },
        "routes": _ROUTES,
    }


def _health() -> dict[str, Any]:
    cfg = load_config()
    return {
        "ok": True,
        "service": "laneora",
        "version": __version__,
        "accounts": len(list_accounts()),
        "allow_multi_screen": bool(cfg.get("allow_multi_screen", True)),
    }


def _session(handler: Any) -> None:
    body = _read_json(handler)
    dash = dashboard_login()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not (_eq(username, dash["username"]) and _eq(password, dash["password"])):
        _send_json(handler, 401, {"ok": False, "error": "Incorrect dashboard login."})
        return
    _send_json(
        handler,
        200,
        {
            "ok": True,
            "token_type": "Bearer",
            "token": ensure_api_token(),
            "username": dash["username"],
        },
    )


def _create(handler: Any) -> None:
    body = _read_json(handler)
    user = create_account(
        str(body.get("username") or ""),
        str(body.get("password") or ""),
        str(body.get("plan") or ""),
        services=body.get("services") if "services" in body else None,
    )
    _send_json(handler, 200, {"ok": True, "user": user})


def _patch(handler: Any, username: str) -> None:
    body = _read_json(handler)
    active = body.get("active") if "active" in body else None
    user = update_account(
        username,
        password=str(body.get("password") or "") or None,
        plan_id=str(body.get("plan") or "") or None,
        extend=bool(body.get("extend")),
        active=None if active is None else bool(active),
        services=body.get("services") if "services" in body else None,
    )
    _send_json(handler, 200, {"ok": True, "user": user, "status": account_status(user)})


def dispatch(handler: Any) -> bool:
    """Handle /api/v1. Return False when the path belongs to another handler."""
    path = _path(handler)
    if path != "/api/v1" and not path.startswith("/api/v1/"):
        return False
    method = handler.command.upper()
    try:
        if method == "OPTIONS":
            _send(handler, 204, b"", "text/plain; charset=utf-8")
            return True
        if path == "/api/v1" and method == "GET":
            _send_json(handler, 200, _index())
            return True
        if path == "/api/v1/health" and method == "GET":
            _send_json(handler, 200, _health())
            return True
        if path == "/api/v1/session" and method == "POST":
            _session(handler)
            return True

        username = _username_from_path(path)
        known = path in {
            "/api/v1",
            "/api/v1/health",
            "/api/v1/session",
            "/api/v1/catalog",
            "/api/v1/users",
            "/api/v1/token/rotate",
        } or username is not None
        if not known:
            _send_json(handler, 404, {"ok": False, "error": "Not found."})
            return True
        if not _require_auth(handler):
            return True

        if path == "/api/v1/catalog" and method == "GET":
            _send_json(handler, 200, {"ok": True, "plans": plan_catalog(), "services": service_catalog()})
            return True
        if path == "/api/v1/users" and method == "GET":
            users = list_accounts()
            _send_json(handler, 200, {"ok": True, "users": users, "summary": _summary(users)})
            return True
        if path == "/api/v1/users" and method == "POST":
            _create(handler)
            return True
        if path == "/api/v1/token/rotate" and method == "POST":
            token = rotate_api_token()
            _send_json(handler, 200, {"ok": True, "token_type": "Bearer", "token": token})
            return True
        if username is not None and method == "GET":
            user = _find_user(username)
            if user is None:
                _send_json(handler, 404, {"ok": False, "error": f"User '{username}' was not found."})
                return True
            _send_json(handler, 200, {"ok": True, "user": user})
            return True
        if username is not None and method == "PATCH":
            _patch(handler, username)
            return True
        if username is not None and method == "DELETE":
            delete_account(username)
            _send_json(handler, 200, {"ok": True})
            return True
        _send_json(handler, 405, {"ok": False, "error": "Method not allowed."})
    except ValueError as exc:
        _send_json(handler, 400, {"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _send_json(handler, 500, {"ok": False, "error": f"API error: {exc}"})
    return True
