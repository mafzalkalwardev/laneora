"""HTTP handlers for the Laneora admin dashboard, served by the Soft shim."""
from __future__ import annotations

import hmac
import json
import secrets
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from server import security
from server.soft_admin_lib import (
    begin_totp,
    change_dashboard_credentials,
    confirm_totp,
    create_account,
    current_session,
    delete_account,
    disable_totp,
    list_accounts,
    login_dashboard,
    revoke_presented_session,
    update_account,
)
from server.subscriptions import account_status, plan_catalog

_HERE = Path(__file__).resolve().parent
_PAGE = _HERE / "admin_dashboard.html"
_MARK = _HERE.parent / "app" / "resources" / "mark.png"
_SESSION_COOKIE = "laneora_admin"
_CSRF_COOKIE = "laneora_csrf"


def _read_cookie(header: str | None, name: str) -> str:
    if not header:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(header)
    except Exception:  # noqa: BLE001
        return ""
    morsel = jar.get(name)
    return morsel.value if morsel else ""


def _csrf_value(handler: Any) -> str:
    existing = _read_cookie(handler.headers.get("Cookie"), _CSRF_COOKIE)
    if 20 <= len(existing) <= 128 and existing.replace("-", "").replace("_", "").isalnum():
        return existing
    return secrets.token_urlsafe(32)


def _cookie(name: str, value: str, handler: Any, *, http_only: bool, max_age: int | None) -> str:
    parts = [f"{name}={value}", "Path=/admin", "SameSite=Lax"]
    if http_only:
        parts.append("HttpOnly")
    if security.cookie_secure(handler):
        parts.append("Secure")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


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


def _security_headers(csp: str) -> list[tuple[str, str]]:
    return [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy", csp),
        ("Cache-Control", "no-store"),
    ]


def _send(
    handler: Any,
    code: int,
    body: bytes,
    content_type: str,
    extra: list[tuple[str, str]] | None = None,
) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    for key, value in extra or []:
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def _finish(
    handler: Any,
    code: int,
    payload: dict[str, Any],
    *,
    session: str | None = None,
    clear_session: bool = False,
    csp: str | None = None,
) -> None:
    policy = csp or "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    headers = _security_headers(policy)
    headers.append(("Set-Cookie", _cookie(_CSRF_COOKIE, _csrf_value(handler), handler, http_only=False, max_age=None)))
    if clear_session:
        headers.append(("Set-Cookie", _cookie(_SESSION_COOKIE, "", handler, http_only=True, max_age=0)))
    elif session:
        headers.append(
            (
                "Set-Cookie",
                _cookie(
                    _SESSION_COOKIE,
                    session,
                    handler,
                    http_only=True,
                    max_age=security.SESSION_TTL_SECONDS,
                ),
            )
        )
    _send(handler, code, _json_bytes(payload), "application/json; charset=utf-8", headers)


def _csrf_blocked(handler: Any) -> bool:
    if not security.origin_allowed(handler):
        _finish(handler, 403, {"ok": False, "error": "Cross-site request blocked."})
        return True
    cookie = _read_cookie(handler.headers.get("Cookie"), _CSRF_COOKIE)
    header = str(handler.headers.get("X-CSRF-Token") or "")
    if not cookie or not header or len(cookie) > 256 or len(header) > 256:
        _finish(handler, 403, {"ok": False, "error": "Missing security token. Reload the page and try again."})
        return True
    if not hmac.compare_digest(cookie, header):
        _finish(handler, 403, {"ok": False, "error": "Missing security token. Reload the page and try again."})
        return True
    return False


def _session_username(handler: Any) -> str | None:
    return current_session(_read_cookie(handler.headers.get("Cookie"), _SESSION_COOKIE))


def _summary(users: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(users), "active": 0, "expired": 0, "disabled": 0, "unset": 0}
    for user in users:
        status = str(user.get("status") or "")
        if status in counts:
            counts[status] += 1
    return counts


def _users_payload() -> dict[str, Any]:
    from server.soft_admin_lib import dashboard_public_state

    users = list_accounts()
    state = dashboard_public_state()
    return {
        "ok": True,
        "users": users,
        "plans": plan_catalog(),
        "summary": _summary(users),
        "totp_enabled": bool(state["totp_enabled"]),
    }


def dispatch(handler: Any) -> bool:
    """Handle /admin routes. Return False when the path is not the dashboard."""
    path = urlparse(handler.path).path
    if path != "/admin" and not path.startswith("/admin/"):
        return False
    method = handler.command
    try:
        if method == "GET" and path in ("/admin", "/admin/"):
            nonce = secrets.token_urlsafe(16)
            page = _PAGE.read_text(encoding="utf-8") if _PAGE.exists() else "Admin page is missing."
            page = page.replace("{{CSP_NONCE}}", nonce)
            policy = (
                "default-src 'self'; img-src 'self'; "
                f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
            )
            headers = _security_headers(policy)
            headers.append(
                ("Set-Cookie", _cookie(_CSRF_COOKIE, _csrf_value(handler), handler, http_only=False, max_age=None))
            )
            _send(handler, 200, page.encode("utf-8"), "text/html; charset=utf-8", headers)
            return True
        if method == "GET" and path == "/admin/mark.png":
            if not _MARK.exists():
                _send(handler, 404, b"", "image/png", _security_headers("default-src 'none'"))
                return True
            _send(handler, 200, _MARK.read_bytes(), "image/png", _security_headers("default-src 'none'"))
            return True
        if method == "POST" and path == "/admin/api/login":
            if _csrf_blocked(handler):
                return True
            ip = security.client_ip(handler)
            if security.throttle_blocked("admin", ip):
                _finish(handler, 429, {"ok": False, "error": "Too many attempts. Wait and try again."})
                return True
            body = _read_json(handler)
            result = login_dashboard(
                str(body.get("username") or ""),
                str(body.get("password") or ""),
                str(body.get("code") or ""),
            )
            if result["status"] == "fail":
                security.throttle_record("admin", ip)
                _finish(handler, 401, {"ok": False, "error": "Incorrect dashboard login."})
                return True
            if result["status"] == "totp":
                _finish(handler, 200, {"ok": True, "totp_required": True})
                return True
            security.throttle_clear("admin", ip)
            _finish(
                handler,
                200,
                {"ok": True, "username": result.get("username") or ""},
                session=str(result["token"]),
            )
            return True
        if method == "POST" and path == "/admin/api/logout":
            if _csrf_blocked(handler):
                return True
            revoke_presented_session(_read_cookie(handler.headers.get("Cookie"), _SESSION_COOKIE))
            _finish(handler, 200, {"ok": True}, clear_session=True)
            return True

        if _session_username(handler) is None:
            _finish(handler, 401, {"ok": False, "error": "Sign in again."})
            return True
        if method == "POST" and _csrf_blocked(handler):
            return True

        if method == "GET" and path == "/admin/api/users":
            _finish(handler, 200, _users_payload())
            return True
        if method == "POST" and path == "/admin/api/users":
            body = _read_json(handler)
            user = create_account(
                str(body.get("username") or ""),
                str(body.get("password") or ""),
                str(body.get("plan") or ""),
            )
            _finish(handler, 200, {"ok": True, "user": user})
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
            )
            _finish(handler, 200, {"ok": True, "user": user, "status": account_status(user)})
            return True
        if method == "POST" and path == "/admin/api/users/delete":
            body = _read_json(handler)
            delete_account(str(body.get("username") or ""))
            _finish(handler, 200, {"ok": True})
            return True
        if method == "POST" and path == "/admin/api/password":
            body = _read_json(handler)
            new_password = str(body.get("password") or "")
            new_username = str(body.get("username") or "").strip()
            token = change_dashboard_credentials(
                str(body.get("current") or ""),
                new_password or None,
                new_username or None,
            )
            _finish(handler, 200, {"ok": True}, session=token)
            return True
        if method == "POST" and path == "/admin/api/totp/setup":
            _read_json(handler)
            started = begin_totp()
            _finish(handler, 200, {"ok": True, "secret": started["secret"], "otpauth": started["otpauth"]})
            return True
        if method == "POST" and path == "/admin/api/totp/confirm":
            body = _read_json(handler)
            codes, token = confirm_totp(str(body.get("code") or ""))
            _finish(handler, 200, {"ok": True, "recovery_codes": codes}, session=token)
            return True
        if method == "POST" and path == "/admin/api/totp/disable":
            body = _read_json(handler)
            token = disable_totp(str(body.get("password") or ""), str(body.get("code") or ""))
            _finish(handler, 200, {"ok": True}, session=token)
            return True
        _finish(handler, 404, {"ok": False, "error": "Not found."})
    except ValueError as exc:
        _finish(handler, 400, {"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"[admin] {type(exc).__name__}")
        _finish(handler, 500, {"ok": False, "error": "Admin error."})
    return True
