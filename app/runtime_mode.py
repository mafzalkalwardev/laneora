"""Startup switches for software rendering and lightweight mode.

Chromium reads these flags when the browser starts, so they have to be applied
before Qt WebEngine is imported. A renderer crash arms software rendering for
the next launch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from app.client_log import log_dir

_SOFTWARE_FLAGS = "--disable-gpu --disable-gpu-compositing"
_SETTINGS = "settings.json"


def settings_path() -> Path:
    return log_dir() / _SETTINGS


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(**updates: object) -> dict:
    data = load_settings()
    data.update(updates)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def _flag_set(argv: list[str] | None, name: str, env_name: str) -> bool:
    args = list(sys.argv if argv is None else argv)
    if name in args:
        return True
    return os.environ.get(env_name, "") == "1"


def software_rendering_enabled(argv: list[str] | None = None) -> bool:
    if _flag_set(argv, "--software-rendering", "LANEORA_SOFTWARE_RENDERING"):
        return True
    if _flag_set(argv, "--lightweight", "LANEORA_LIGHTWEIGHT"):
        return True
    settings = load_settings()
    return bool(settings.get("software_rendering") or settings.get("lightweight"))


def lightweight_enabled(argv: list[str] | None = None) -> bool:
    if _flag_set(argv, "--lightweight", "LANEORA_LIGHTWEIGHT"):
        return True
    return bool(load_settings().get("lightweight"))


def chromium_flags(existing: str, *, software: bool) -> str:
    flags = str(existing or "").strip()
    if not software:
        return flags
    for piece in _SOFTWARE_FLAGS.split():
        if piece not in flags.split():
            flags = f"{flags} {piece}".strip()
    return flags


def apply_startup_flags(argv: list[str] | None = None) -> None:
    """Set process flags before Qt WebEngine is imported."""
    software = software_rendering_enabled(argv)
    if software:
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = chromium_flags(
            os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
            software=True,
        )
    from app.client_log import client_log

    client_log(
        "startup",
        software_rendering=software,
        lightweight=lightweight_enabled(argv),
    )


def arm_software_rendering(reason: str) -> None:
    save_settings(software_rendering=True)
    from app.client_log import client_log

    client_log("arm-software-rendering", reason=reason)


def lightweight_cache_bytes() -> int:
    return 8 * 1024 * 1024
