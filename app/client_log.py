"""A log the client can send. It never stores passwords, cookies, or proxy secrets."""
from __future__ import annotations

import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
_MAX_BYTES = 200_000
_QUERY = re.compile(r"\?[^\s\"']*")
_USERINFO = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
_COOKIE_HEADER = re.compile(r"(?i)(cookie|set-cookie|authorization)\s*[:=]\s*\S+")

_SECRET_FIELDS = {
    "password",
    "passwd",
    "secret",
    "cookie",
    "cookies",
    "authorization",
    "proxy_password",
    "pd",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
}


def log_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(root) / "Laneora"
    return Path.home() / ".laneora"


def log_path() -> Path:
    return log_dir() / "laneora.log"


def redact_text(value: str) -> str:
    text = _USERINFO.sub("://*:*@", str(value))
    text = _QUERY.sub("", text)
    text = _COOKIE_HEADER.sub(r"\1=<redacted>", text)
    return text


def client_log(event: str, **fields: object) -> None:
    """Append one line. Field values are redacted. Secret field names are dropped."""
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [when, redact_text(event)]
    for key, value in fields.items():
        if str(key).lower() in _SECRET_FIELDS:
            continue
        parts.append(f"{key}={redact_text(value)}")
    line = " ".join(parts)
    path = log_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if path.stat().st_size > _MAX_BYTES:
            kept = path.read_text(encoding="utf-8")[-_MAX_BYTES // 2 :]
            path.write_text(kept, encoding="utf-8")
