"""Load search API for any app that can reach the Soft server.

Sign in with a Laneora username and password. The token can search loads and
open one load's details. It cannot create users, change plans, or open the
admin desk.
"""
from __future__ import annotations

import hmac
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from app import __version__
from server.load_board import BoardError, load_detail, search_loads
from server.soft_admin_lib import ensure_api_token, load_local_users
from server.subscriptions import denial_payload

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
}

_ROUTES: list[dict[str, Any]] = [
    {"method": "GET", "path": "/api/v1", "auth": False, "description": "This index."},
    {"method": "GET", "path": "/api/v1/health", "auth": False, "description": "The server is up."},
    {
        "method": "POST",
        "path": "/api/v1/session",
        "auth": False,
        "description": "Exchange a Laneora username and password for a search token.",
    },
    {
        "method": "POST",
        "path": "/api/v1/loads/search",
        "auth": True,
        "description": "Search loads on the board session stored in Laneora.",
    },
    {
        "method": "GET",
        "path": "/api/v1/loads/detail",
        "auth": True,
        "description": "One load's extra details. Query: search_id, match_id.",
    },
]


def _eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def issue_token(username: str) -> str:
    secret = ensure_api_token().encode("utf-8")
    name = username.strip()
    mac = hmac.new(secret, name.lower().encode("utf-8"), "sha256").hexdigest()
    return f"{name}.{mac}"


def token_username(token: str) -> str | None:
    if "." not in token:
        return None
    name, mac = token.rsplit(".", 1)
    if not name or not mac:
        return None
    expected = issue_token(name).rsplit(".", 1)[1]
    if not _eq(mac, expected):
        return None
    return name


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


def _account(username: str, password: str) -> dict[str, Any]:
    wanted = username.strip().lower()
    secret = password.strip().lower()
    for user in load_local_users():
        if str(user.get("username") or "").lower() != wanted:
            continue
        if str(user.get("password") or "").lower() != secret:
            break
        denied = denial_payload(user)
        if denied:
            raise PermissionError(str(denied.get("message") or "This account cannot search."))
        return user
    raise PermissionError("Incorrect Laneora login.")


def _session(handler: Any) -> None:
    body = _read_json(handler)
    try:
        user = _account(str(body.get("username") or ""), str(body.get("password") or ""))
    except PermissionError as exc:
        _send_json(handler, 401, {"ok": False, "error": str(exc)})
        return
    name = str(user.get("username") or "")
    _send_json(
        handler,
        200,
        {"ok": True, "token_type": "Bearer", "token": issue_token(name), "username": name, "scope": "loads"},
    )


def _caller(handler: Any) -> str | None:
    username = token_username(_presented_token(handler))
    if username is None:
        _send_json(handler, 401, {"ok": False, "error": "Send Authorization: Bearer <token> from POST /api/v1/session."})
        return None
    return username


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
            _send_json(
                handler,
                200,
                {
                    "ok": True,
                    "service": "laneora",
                    "version": __version__,
                    "scope": "loads",
                    "auth": "Authorization: Bearer <token>",
                    "session": {
                        "method": "POST",
                        "path": "/api/v1/session",
                        "body": {"username": "Laneora username", "password": "Laneora password"},
                    },
                    "routes": _ROUTES,
                },
            )
            return True
        if path == "/api/v1/health" and method == "GET":
            _send_json(handler, 200, {"ok": True, "service": "laneora", "version": __version__})
            return True
        if path == "/api/v1/session" and method == "POST":
            _session(handler)
            return True
        if path in ("/api/v1/loads/search", "/api/v1/loads/detail"):
            username = _caller(handler)
            if username is None:
                return True
            if path == "/api/v1/loads/search" and method == "POST":
                _send_json(handler, 200, search_loads(username, _read_json(handler)))
                return True
            if path == "/api/v1/loads/detail" and method == "GET":
                query = parse_qs(urlparse(handler.path).query)
                search_id = (query.get("search_id") or [""])[0]
                match_id = (query.get("match_id") or [""])[0]
                _send_json(handler, 200, load_detail(username, search_id, match_id))
                return True
            _send_json(handler, 405, {"ok": False, "error": "Method not allowed."})
            return True
        _send_json(handler, 404, {"ok": False, "error": "Not found. This API searches loads only."})
    except PermissionError as exc:
        _send_json(handler, 401, {"ok": False, "error": str(exc)})
    except BoardError as exc:
        _send_json(handler, exc.status, {"ok": False, "error": str(exc)})
    except ValueError as exc:
        _send_json(handler, 400, {"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _send_json(handler, 500, {"ok": False, "error": f"API error: {exc}"})
    return True
