"""
Soft-compatible API shim (replaces soft.awwthat.com /authenticate when Soft is down).

Same contracts as Soft:
  GET /authenticate?username=&key=&value=&is_alive=
  GET /logger?uva=
  GET /linetext
  GET /latest_version
  HEAD|GET /update

Multi-PC + same IP:
  - data/soft_config.json  shared_proxy → every auth payload uses px/p/pu/pd
  - allow_multi_screen=true → many PCs can heartbeat the same Soft user
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import PASSPHRASE, __version__  # noqa: E402
from app.config import USERS_FILE  # noqa: E402
from app.crypto_util import encrypt  # noqa: E402
from server.admin_api import dispatch as dispatch_admin  # noqa: E402
from server.soft_admin_lib import (  # noqa: E402
    DEFAULT_STREAMS,
    apply_shared_proxy_to_user,
    ensure_dashboard_login,
    load_config,
    load_local_users,
)
from server.subscriptions import account_searches, denial_payload  # noqa: E402

HOST = __import__("os").environ.get("LANEORA_SOFT_HOST", "0.0.0.0")
PORT = int(__import__("os").environ.get("LANEORA_SOFT_PORT", "8787"))

# uva -> expected logger echo (value)
_LIVE: dict[str, str] = {}
# soft username -> currently allowed uva (only when allow_multi_screen is false)
_PRIMARY: dict[str, str] = {}


def _load_json_users(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("users") or [])


def _all_accounts() -> list[dict]:
    cfg = load_config()
    by_name: dict[str, dict] = {}
    for user in load_local_users():
        name = str(user.get("username", "")).strip().lower()
        if name:
            by_name[name] = apply_shared_proxy_to_user(dict(user), cfg)
    for user in _load_json_users(USERS_FILE):
        name = str(user.get("username", "")).strip().lower()
        if not name:
            continue
        if name in by_name:
            # local_users.json is source of truth for Soft passwords; do not overwrite.
            apply_shared_proxy_to_user(by_name[name], cfg)
            continue
        account = {
            "username": user.get("username"),
            "password": user.get("password"),
            "active": True,
            "active_subs": ["one", "power"],
            "streams": DEFAULT_STREAMS,
        }
        by_name[name] = apply_shared_proxy_to_user(account, cfg)
    return list(by_name.values())


_WS_RE = re.compile(r"^[\s\u200B\u00A0]+|[\s\u200B\u00A0]+$")


def _client_secret(value: str) -> str:
    """Same fold the v3.0.0 desktop client applies before GET /authenticate."""
    return _WS_RE.sub("", str(value or "").strip().lower())


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _is_pbkdf2_hash(value: str) -> bool:
    parts = str(value or "").split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256" or not parts[1].isdigit():
        return False
    rounds = int(parts[1])
    return 1 <= rounds <= 5_000_000


def _verify_pbkdf2(password: str, encoded: str) -> bool:
    """Check a pbkdf2_sha256$rounds$salt$hash string. Invalid strings do not match."""
    try:
        if not _is_pbkdf2_hash(encoded):
            return False
        _algo, rounds_text, salt_text, digest_text = encoded.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64d(salt_text),
            int(rounds_text),
        )
        return hmac.compare_digest(digest, _b64d(digest_text))
    except (ValueError, TypeError):
        return False


def _find_user(username: str, password: str) -> dict | None:
    username = _client_secret(username)
    password = _client_secret(password)
    if not username or not password:
        return None
    for user in _all_accounts():
        if _client_secret(str(user.get("username", ""))) != username:
            continue
        plain = user.get("password")
        plain_text = "" if plain is None else str(plain)
        # Restored accounts still have a plaintext password. Keep that compare.
        if plain_text and not _is_pbkdf2_hash(plain_text):
            if plain_text.lower() != password:
                return None
            return user
        # Hash-only account (pbkdf2_sha256$600000$...). No plaintext fallback.
        encoded = str(user.get("password_hash") or "")
        if not encoded and _is_pbkdf2_hash(plain_text):
            encoded = plain_text
        if not encoded or not _verify_pbkdf2(password, encoded):
            return None
        return user
    return None


def _build_auth_payload(user: dict) -> dict:
    cfg = load_config()
    user = apply_shared_proxy_to_user(dict(user), cfg)
    streams = user.get("streams") or DEFAULT_STREAMS
    active = user.get("active_subs") or list(streams.keys())
    if isinstance(active, str):
        active_list = [s for s in active.split(",") if s]
    else:
        active_list = list(active)
    payload: dict = {
        "status": "okie",
        "p": str(user.get("p", "0")),
        "px": str(user.get("px", "none")),
        "pu": str(user.get("pu", "")),
        "pd": str(user.get("pd", "")),
        "active_subs": ",".join(active_list),
        "max_searches": account_searches(user),
    }
    for name in active_list:
        stream = streams.get(name) or DEFAULT_STREAMS.get(name) or {
            "url": "https://one.dat.com",
            "store": [],
            "lst": "{}",
            "sst": "",
        }
        payload[name] = encrypt(PASSPHRASE, json.dumps(stream))
    return payload


def _register_session(username: str, value: str, is_alive: str) -> str:
    uva = f"{username.strip().lower()}:{value}:{is_alive}"
    _LIVE[uva] = str(value)
    cfg = load_config()
    if cfg.get("allow_multi_screen", True):
        return uva
    # Single-screen Soft behavior: newest login wins; older PCs fail logger check
    _PRIMARY[username.strip().lower()] = uva
    return uva


def _logger_echo(uva: str) -> str:
    cfg = load_config()
    parts = uva.split(":")
    username = parts[0] if parts else ""
    value = parts[1] if len(parts) >= 2 else ""

    if cfg.get("allow_multi_screen", True):
        if uva not in _LIVE:
            _LIVE[uva] = value
        return _LIVE.get(uva, value)

    primary = _PRIMARY.get(username)
    if primary is None:
        _PRIMARY[username] = uva
        _LIVE[uva] = value
        return value
    if primary != uva:
        # Soft-style: wrong echo → client shows Multiple Screens not allowed
        return "0"
    return _LIVE.get(uva, value)


class Handler(BaseHTTPRequestHandler):
    server_version = "LaneoraSoftShim/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[soft-shim] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: str | bytes, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/update":
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if dispatch_admin(self):
            return
        self._send(404, "not found")

    def do_GET(self) -> None:  # noqa: N802
        if dispatch_admin(self):
            return
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path
        cfg = load_config()

        if path == "/latest_version":
            self._send(200, __version__)
            return
        if path == "/linetext":
            multi = "multi-PC ON" if cfg.get("allow_multi_screen", True) else "single-screen"
            proxy = (cfg.get("shared_proxy") or {}).get("px", "none")
            self._send(200, f"Laneora Soft shim — {multi}; shared proxy={proxy}")
            return
        if path == "/update":
            self._send(200, b"")
            return
        if path == "/authenticate":
            username = (qs.get("username") or [""])[0]
            key = (qs.get("key") or [""])[0]
            value = (qs.get("value") or [""])[0]
            is_alive = (qs.get("is_alive") or [""])[0]
            user = _find_user(username, key)
            if not user:
                self._send(200, "0")
                return
            denied = denial_payload(user)
            if denied:
                self._send(200, json.dumps(denied), "application/json; charset=utf-8")
                return
            _register_session(username, str(value), str(is_alive))
            self._send(200, json.dumps(_build_auth_payload(user)), "application/json; charset=utf-8")
            return
        if path == "/logger":
            uva = (qs.get("uva") or [""])[0]
            self._send(200, _logger_echo(uva))
            return
        if path in ("/", "/health"):
            proxy = cfg.get("shared_proxy") or {}
            self._send(
                200,
                json.dumps(
                    {
                        "ok": True,
                        "users": len(_all_accounts()),
                        "allow_multi_screen": bool(cfg.get("allow_multi_screen", True)),
                        "shared_proxy_host": proxy.get("px"),
                    }
                ),
                "application/json",
            )
            return
        self._send(404, "not found")


def ensure_running(host: str = HOST, port: int = PORT) -> str:
    import socket
    import threading

    # Bind may be 0.0.0.0, but clients must connect to loopback (WinError 10049 on 0.0.0.0).
    bind_host = host or "0.0.0.0"
    connect_host = "127.0.0.1" if bind_host in ("0.0.0.0", "::", "") else bind_host
    base = f"http://{connect_host}:{port}"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((connect_host, port)) == 0:
            return base

    httpd = ThreadingHTTPServer((bind_host, port), Handler)

    def _serve() -> None:
        httpd.serve_forever()

    threading.Thread(target=_serve, daemon=True, name="laneora-soft-shim").start()
    return base


def main() -> None:
    cfg = load_config()
    users = _all_accounts()
    proxy = cfg.get("shared_proxy") or {}
    ensure_dashboard_login()
    print(f"Laneora Soft shim on http://{HOST}:{PORT}")
    print(f"Admin dashboard: http://127.0.0.1:{PORT}/admin")
    print(f"multi_screen={cfg.get('allow_multi_screen', True)}  shared_proxy={proxy.get('px')}:{proxy.get('p')}")
    print(f"Accounts ({len(users)}):")
    for user in users:
        # Do not log Soft passwords (data secrets).
        print(f"  - {user.get('username')}  px={user.get('px')}")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
