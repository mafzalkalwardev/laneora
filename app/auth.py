"""soft.awwthat.com authenticate + logger heartbeat."""
from __future__ import annotations

import json
import random
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

import requests

from app.config import SERVER_URL

_WS_RE = re.compile(r"^[\s\u200B\u00A0]+|[\s\u200B\u00A0]+$")


def normalize_credential(value: str) -> str:
    value = value.strip().lower()
    return _WS_RE.sub("", value)


@dataclass
class AuthSession:
    username: str
    password: str
    value: int
    is_alive: int
    resp: dict[str, Any]

    @property
    def log_data(self) -> str:
        return f"{self.username}:{self.value}:{self.is_alive}"

    @property
    def proxy_host(self) -> str:
        return str(self.resp.get("px", ""))

    @property
    def proxy_port(self) -> int:
        return int(self.resp.get("p", 0) or 0)

    @property
    def proxy_user(self) -> str:
        return str(self.resp.get("pu", ""))

    @property
    def proxy_password(self) -> str:
        return str(self.resp.get("pd", ""))

    @property
    def active_subs(self) -> list[str]:
        raw = str(self.resp.get("active_subs", "") or "")
        return [s for s in raw.split(",") if s]


class AuthError(Exception):
    pass


def _parse_authenticate_body(raw: str, status_code: int) -> Any:
    text = (raw or "").strip()
    if text == "0":
        return 0
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if status_code >= 500:
            raise AuthError(
                f"Soft server error (HTTP {status_code}). "
                f"{SERVER_URL}/authenticate is down or crashing — not a Laneora roster issue."
            ) from exc
        if "<html" in text.lower():
            raise AuthError(
                f"Soft returned HTML instead of JSON (HTTP {status_code}). "
                "Check soft.awwthat.com /authenticate."
            ) from exc
        raise AuthError(
            f"Unexpected authenticate response (HTTP {status_code}): {text[:160]!r}"
        ) from exc


def authenticate(username: str, password: str) -> AuthSession:
    username = normalize_credential(username)
    password = normalize_credential(password)
    if not username or not password:
        raise AuthError("Enter username and password.")

    value = random.randint(1, 99_999_999)
    is_alive = random.randint(1, 9999)
    try:
        verify = requests.get(
            SERVER_URL + "/authenticate",
            params={
                "username": username,
                "key": password,
                "value": value,
                "is_alive": is_alive,
            },
            headers={"Accept": "application/json"},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Could not reach Soft ({SERVER_URL}): {exc}") from exc

    resp = _parse_authenticate_body(verify.text, verify.status_code)

    if isinstance(resp, dict) and resp.get("message") and resp.get("status") != "okie":
        # Laravel-style {"message":"Server Error"}
        raise AuthError(
            f"Soft authenticate failed (HTTP {verify.status_code}): {resp.get('message')}. "
            "Fix soft.awwthat.com /authenticate, or temporarily use the local API for UI tests."
        )

    if resp == 0 or resp == "0":
        raise AuthError("Incorrect username or password.")
    if not isinstance(resp, dict) or resp.get("status") != "okie":
        raise AuthError("Incorrect username or password.")

    return AuthSession(
        username=username,
        password=password,
        value=value,
        is_alive=is_alive,
        resp=resp,
    )


def start_logger_heartbeat(
    session: AuthSession,
    on_violation: Callable[[], None],
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    stop_event = stop_event or threading.Event()

    def _loop() -> None:
        while not stop_event.is_set():
            try:
                chk = requests.get(
                    SERVER_URL + "/logger",
                    params={"uva": session.log_data},
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                if str(chk.text) == str(session.value):
                    stop_event.wait(60)
                    continue
                on_violation()
                return
            except Exception as exc:  # noqa: BLE001 — match original continue-on-error
                print(exc)
                stop_event.wait(5)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread


def reauthenticate(session: AuthSession) -> AuthSession:
    """Refresh proxy/stream payloads with the same session tokens."""
    try:
        verify = requests.get(
            SERVER_URL + "/authenticate",
            params={
                "username": session.username,
                "key": session.password,
                "value": session.value,
                "is_alive": session.is_alive,
            },
            headers={"Accept": "application/json"},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Could not reach Soft ({SERVER_URL}): {exc}") from exc

    resp = _parse_authenticate_body(verify.text, verify.status_code)
    if not isinstance(resp, dict) or resp.get("status") != "okie":
        raise AuthError("Re-authenticate failed")
    session.resp = resp
    return session
