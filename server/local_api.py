"""
Local Soft-compatible API for Laneora testing.

Endpoints (same shapes as soft.awwthat.com):
  GET /authenticate?username=&key=&value=&is_alive=
  GET /logger?uva=
  GET /linetext
  GET /latest_version
  HEAD|GET /update  (stub empty body)

Users live in data/local_users.json (not the Soft credentials roster).
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import PASSPHRASE, __version__  # noqa: E402
from app.config import LOCAL_USERS_FILE  # noqa: E402
from app.crypto_util import encrypt  # noqa: E402

HOST = "127.0.0.1"
PORT = 8787

# session token -> expected logger echo (username:value:is_alive -> value)
_LIVE: dict[str, str] = {}


def _load_users() -> list[dict]:
    if not LOCAL_USERS_FILE.exists():
        return []
    data = json.loads(LOCAL_USERS_FILE.read_text(encoding="utf-8"))
    return list(data.get("users") or [])


def _find_user(username: str, password: str) -> dict | None:
    username = username.strip().lower()
    password = password.strip().lower()
    for user in _load_users():
        if str(user.get("username", "")).lower() != username:
            continue
        if str(user.get("password", "")).lower() != password:
            continue
        if user.get("active", True) is False:
            return None
        return user
    return None


def _build_auth_payload(user: dict) -> dict:
    streams = user.get("streams") or {}
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
    }
    for name in active_list:
        stream = streams.get(name) or {
            "url": "https://one.dat.com",
            "store": [],
            "lst": "{}",
            "sst": "",
        }
        payload[name] = encrypt(PASSPHRASE, json.dumps(stream))
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "LaneoraLocal/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[local-api] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: str | bytes, content_type: str = "text/plain; charset=utf-8") -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/update":
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path == "/latest_version":
            self._send(200, __version__)
            return

        if path == "/linetext":
            self._send(200, "Laneora local test server — inject users in data/users.json")
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
            uva = f"{username.strip().lower()}:{value}:{is_alive}"
            _LIVE[uva] = str(value)
            payload = _build_auth_payload(user)
            self._send(200, json.dumps(payload), "application/json; charset=utf-8")
            return

        if path == "/logger":
            uva = (qs.get("uva") or [""])[0]
            expected = _LIVE.get(uva)
            if expected is None:
                # unknown session — treat as ok for single-screen local testing
                # by echoing the middle token when present
                parts = uva.split(":")
                expected = parts[1] if len(parts) >= 2 else ""
                _LIVE[uva] = expected
            self._send(200, expected)
            return

        self._send(404, "not found")


def main() -> None:
    LOCAL_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOCAL_USERS_FILE.exists():
        raise SystemExit(f"Missing {LOCAL_USERS_FILE}")
    users = _load_users()
    print(f"Laneora local API on http://{HOST}:{PORT}")
    print(f"Users file: {LOCAL_USERS_FILE} ({len(users)} users)")
    print("Seeded logins (username / password):")
    for user in users:
        print(f"  - {user.get('username')} / {user.get('password')}")
    print("Use: $env:LANEORA_SERVER_URL='http://127.0.0.1:8787'")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
