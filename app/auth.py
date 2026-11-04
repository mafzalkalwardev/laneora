"""soft.awwthat.com authenticate + logger heartbeat."""
from __future__ import annotations

import json
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from app import SERVER_URL

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
        return int(self.resp.get("p", 0))

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


def authenticate(username: str, password: str) -> AuthSession:
    username = normalize_credential(username)
    password = normalize_credential(password)
    value = random.randint(1, 99_999_999)
    is_alive = random.randint(1, 9999)
    verify = requests.get(
        SERVER_URL + "/authenticate",
        params={
            "username": username,
            "key": password,
            "value": value,
            "is_alive": is_alive,
        },
        timeout=60,
    )
    raw = verify.text
    try:
        resp = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthError("Unexpected authenticate response") from exc
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
    verify = requests.get(
        SERVER_URL + "/authenticate",
        params={
            "username": session.username,
            "key": session.password,
            "value": session.value,
            "is_alive": session.is_alive,
        },
        timeout=60,
    )
    resp = json.loads(verify.text)
    if not isinstance(resp, dict) or resp.get("status") != "okie":
        raise AuthError("Re-authenticate failed")
    session.resp = resp
    return session
