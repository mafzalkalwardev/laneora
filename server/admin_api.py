"""HTTP handlers for the Laneora admin dashboard, served by the Soft shim."""
from __future__ import annotations

import hmac
import json
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from server.soft_admin_lib import (
    create_account,
    dashboard_login,
    delete_account,
    list_accounts,
    set_dashboard_password,
    update_account,
)
from app.services import service_catalog
from server.subscriptions import account_status, plan_catalog

_HERE = Path(__file__).resolve().parent
_PAGE = _HERE / "admin_dashboard.html"
_MARK = _HERE.parent / "app" / "resources" / "mark.png"


def _eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _cookie_token(header: str | None) -> str:
    if not header:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(header)
    except Exception:  # noqa: BLE001
        return ""
    morsel = jar.get("laneora_admin")
    return morsel.value if morsel else ""


def _sign(username: str) -> str:
    # Keyed with the dashboard password so a password change signs out old browsers.
    secret = dashboard_login()["password"].encode("utf-8")
    mac = hmac.new(secret, username.encode("utf-8"), "sha256").hexdigest()
    return f"{username}.{mac}"


def _session_username(header: str | None) -> str | None:
    token = _cookie_token(header)
    if "." not in token:
        return None
    username, mac = token.rsplit(".", 1)
    expected = _sign(username).rsplit(".", 1)[1]
    if not hmac.compare_digest(mac, expected):
        return None
    if username != dashboard_login()["username"]:
        return None
    return username


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


def _send(handler: Any, code: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in (extra or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def _send_json(handler: Any, code: int, payload: dict[str, Any], extra: dict[str, str] | None = None) -> None:
    _send(handler, code, _json_bytes(payload), "application/json; charset=utf-8", extra)


def _unauthorized(handler: Any) -> None:
    _send_json(handler, 401, {"ok": False, "error": "Sign in again."})


def _summary(users: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(users), "active": 0, "expired": 0, "disabled": 0, "unset": 0}
    for user in users:
        status = str(user.get("status") or "")
        if status in counts:
            counts[status] += 1
    return counts


def dispatch(handler: Any) -> bool:
    """Handle /admin routes. Return False when the path is not the dashboard."""
    path = urlparse(handler.path).path
    if path != "/admin" and not path.startswith("/admin/"):
        return False
    method = handler.command
    try:
        if method == "GET" and path in ("/admin", "/admin/"):
            page = _PAGE.read_bytes() if _PAGE.exists() else b"Admin page is missing."
            _send(handler, 200, page, "text/html; charset=utf-8")
            return True
        if method == "GET" and path == "/admin/mark.png":
            if not _MARK.exists():
                _send(handler, 404, b"", "image/png")
                return True
            _send(handler, 200, _MARK.read_bytes(), "image/png")
            return True
        if method == "POST" and path == "/admin/api/login":
            body = _read_json(handler)
            dash = dashboard_login()
            username = str(body.get("username") or "").strip()
            password = str(body.get("password") or "")
            if not (_eq(username, dash["username"]) and _eq(password, dash["password"])):
                _send_json(handler, 401, {"ok": False, "error": "Incorrect dashboard login."})
                return True
            token = _sign(dash["username"])
            _send_json(
                handler,
                200,
                {"ok": True, "username": dash["username"]},
                {"Set-Cookie": f"laneora_admin={token}; HttpOnly; Path=/admin; SameSite=Lax"},
            )
            return True
        if method == "POST" and path == "/admin/api/logout":
            _send_json(
                handler,
                200,
                {"ok": True},
                {"Set-Cookie": "laneora_admin=; HttpOnly; Path=/admin; Max-Age=0; SameSite=Lax"},
            )
            return True

        if _session_username(handler.headers.get("Cookie")) is None:
            _unauthorized(handler)
            return True

        if method == "GET" and path == "/admin/api/users":
            users = list_accounts()
            _send_json(
                handler,
                200,
                {
                    "ok": True,
                    "users": users,
                    "plans": plan_catalog(),
                    "services": service_catalog(),
                    "summary": _summary(users),
                },
            )
            return True
        if method == "POST" and path == "/admin/api/users":
            body = _read_json(handler)
            user = create_account(
                str(body.get("username") or ""),
                str(body.get("password") or ""),
                str(body.get("plan") or ""),
                services=body.get("services") if "services" in body else None,
            )
            _send_json(handler, 200, {"ok": True, "user": user})
            return True
        if method == "POST" and path == "/admin/api/users/update":
            body = _read_json(handler)
            active = body.get("active")
            user = update_account(
                str(body.get("username") or ""),
                password=str(body.get("password") or "") or None,
                plan_id=str(body.get("plan") or "") or None,
                extend=bool(body.get("extend")),
                active=None if active is None else bool(active),
                services=body.get("services") if "services" in body else None,
            )
            _send_json(handler, 200, {"ok": True, "user": user, "status": account_status(user)})
            return True
        if method == "POST" and path == "/admin/api/users/delete":
            body = _read_json(handler)
            delete_account(str(body.get("username") or ""))
            _send_json(handler, 200, {"ok": True})
            return True
        if method == "POST" and path == "/admin/api/password":
            body = _read_json(handler)
            set_dashboard_password(str(body.get("current") or ""), str(body.get("password") or ""))
            dash = dashboard_login()
            token = _sign(dash["username"])
            _send_json(
                handler,
                200,
                {"ok": True},
                {"Set-Cookie": f"laneora_admin={token}; HttpOnly; Path=/admin; SameSite=Lax"},
            )
            return True
        _send_json(handler, 404, {"ok": False, "error": "Not found."})
    except ValueError as exc:
        _send_json(handler, 400, {"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _send_json(handler, 500, {"ok": False, "error": f"Admin error: {exc}"})
    return True
