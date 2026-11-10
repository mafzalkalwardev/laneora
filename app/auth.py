"""soft.awwthat.com authenticate + logger heartbeat (with Soft-shim fallback)."""
from __future__ import annotations

import json
import random
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

import requests

from app.config import SERVER_URL, SOFT_FALLBACK, SOFT_FALLBACK_URL
from app.services import DAT, normalize_services

_WS_RE = re.compile(r"^[\s\u200B\u00A0]+|[\s\u200B\u00A0]+$")

# Active Soft base URL for this process (may switch to local shim).
_ACTIVE_SERVER = SERVER_URL


def normalize_credential(value: str) -> str:
    value = value.strip().lower()
    return _WS_RE.sub("", value)


def active_server_url() -> str:
    return _ACTIVE_SERVER


@dataclass
class AuthSession:
    username: str
    password: str
    value: int
    is_alive: int
    resp: dict[str, Any]
    server_url: str = SERVER_URL

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

    @property
    def services(self) -> list[str]:
        """Modules this login may open. Older servers omit the field; that is DAT Search only."""
        if "services" not in self.resp:
            return [DAT]
        return normalize_services(self.resp.get("services"))


class AuthError(Exception):
    pass


def _parse_authenticate_body(raw: str, status_code: int, server: str) -> Any:
    text = (raw or "").strip()
    if text == "0":
        return 0
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if status_code >= 500:
            raise AuthError(
                f"Soft server error (HTTP {status_code}). "
                f"{server}/authenticate is down or crashing — not a Laneora roster issue."
            ) from exc
        if "<html" in text.lower():
            raise AuthError(
                f"Soft returned HTML instead of JSON (HTTP {status_code}). "
                f"Check {server}/authenticate."
            ) from exc
        raise AuthError(
            f"Unexpected authenticate response (HTTP {status_code}): {text[:160]!r}"
        ) from exc


def _soft_down(status_code: int, body: str) -> bool:
    if status_code >= 500:
        return True
    text = (body or "").strip()
    if not text:
        return status_code >= 500
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return status_code >= 500 and "<html" in text.lower()
    return isinstance(data, dict) and data.get("message") == "Server Error" and data.get("status") != "okie"


def _normalize_soft_base(url: str) -> str:
    """Clients cannot connect to 0.0.0.0 (WinError 10049) — use loopback."""
    url = (url or "").rstrip("/")
    if "://0.0.0.0:" in url or url.startswith("http://0.0.0.0") or url.startswith("https://0.0.0.0"):
        return url.replace("://0.0.0.0", "://127.0.0.1", 1)
    return url


def _ensure_shim() -> str:
    # Prefer an already-running Soft on loopback before spawning another.
    try:
        probe = requests.get(SOFT_FALLBACK_URL + "/latest_version", timeout=2)
        if probe.status_code < 500:
            return _normalize_soft_base(SOFT_FALLBACK_URL)
    except requests.RequestException:
        pass

    from server.soft_shim import ensure_running

    return _normalize_soft_base(ensure_running())


def _authenticate_against(server: str, username: str, password: str, value: int, is_alive: int) -> tuple[Any, int, str]:
    verify = requests.get(
        server + "/authenticate",
        params={
            "username": username,
            "key": password,
            "value": value,
            "is_alive": is_alive,
        },
        headers={"Accept": "application/json"},
        timeout=60,
    )
    return _parse_authenticate_body(verify.text, verify.status_code, server), verify.status_code, verify.text


def authenticate(username: str, password: str) -> AuthSession:
    global _ACTIVE_SERVER

    username = normalize_credential(username)
    password = normalize_credential(password)
    if not username or not password:
        raise AuthError("Enter username and password.")

    value = random.randint(1, 99_999_999)
    is_alive = random.randint(1, 9999)

    servers = [SERVER_URL]
    used_fallback = False

    first_error: Exception | None = None
    resp: Any = None
    status = 0
    raw = ""

    try:
        resp, status, raw = _authenticate_against(SERVER_URL, username, password, value, is_alive)
        if _soft_down(status, raw):
            print(f"[auth] Soft primary HTTP {status} — starting Soft shim fallback…")
            resp = None
        else:
            _ACTIVE_SERVER = SERVER_URL
    except (requests.RequestException, AuthError) as first_exc:
        first_error = first_exc
        if not SOFT_FALLBACK:
            if isinstance(first_exc, AuthError):
                raise
            raise AuthError(f"Could not reach Soft ({SERVER_URL}): {first_exc}") from first_exc
        print(f"[auth] Soft primary failed ({SERVER_URL}): {first_exc}; trying Soft shim…")
        resp, status, raw = None, 500, ""

    if resp is None and SOFT_FALLBACK:
        try:
            shim = _ensure_shim()
            servers.append(shim)
            resp, status, raw = _authenticate_against(shim, username, password, value, is_alive)
            used_fallback = True
            _ACTIVE_SERVER = shim
        except (requests.RequestException, AuthError) as shim_exc:
            if first_error is not None:
                raise AuthError(
                    f"Soft is down ({SERVER_URL}) and Soft shim also failed ({SOFT_FALLBACK_URL}): {shim_exc}"
                ) from shim_exc
            raise AuthError(
                f"Soft authenticate failed and Soft shim failed: {shim_exc}"
            ) from shim_exc
    elif resp is None:
        raise AuthError(
            f"Soft authenticate failed (HTTP {status}). "
            "soft.awwthat.com /authenticate is crashing; enable Soft shim fallback or fix Soft host."
        )

    if isinstance(resp, dict) and resp.get("message") and resp.get("status") != "okie":
        code = str(resp.get("status") or "")
        if code in {"expired", "disabled"}:
            raise AuthError(str(resp.get("message")))
        raise AuthError(
            f"Soft authenticate failed (HTTP {status}): {resp.get('message')}. "
            "Fix soft.awwthat.com /authenticate, or use Soft shim fallback."
        )

    if resp == 0 or resp == "0":
        raise AuthError("Incorrect username or password.")
    if not isinstance(resp, dict) or resp.get("status") != "okie":
        raise AuthError("Incorrect username or password.")

    server_used = _ACTIVE_SERVER if used_fallback else SERVER_URL
    if used_fallback:
        print(f"[auth] Authenticated via Soft shim {server_used} (soft.awwthat.com still broken)")

    return AuthSession(
        username=username,
        password=password,
        value=value,
        is_alive=is_alive,
        resp=resp,
        server_url=server_used,
    )


def start_logger_heartbeat(
    session: AuthSession,
    on_violation: Callable[[], None],
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    stop_event = stop_event or threading.Event()
    base = session.server_url or active_server_url()

    def _loop() -> None:
        while not stop_event.is_set():
            try:
                chk = requests.get(
                    base + "/logger",
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
    base = session.server_url or active_server_url()
    try:
        verify = requests.get(
            base + "/authenticate",
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
        raise AuthError(f"Could not reach Soft ({base}): {exc}") from exc

    resp = _parse_authenticate_body(verify.text, verify.status_code, base)
    if not isinstance(resp, dict) or resp.get("status") != "okie":
        raise AuthError("Re-authenticate failed")
    session.resp = resp
    return session
