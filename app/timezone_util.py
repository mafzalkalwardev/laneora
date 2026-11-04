"""Timezone sync via ipinfo.io + Windows tzutil."""
from __future__ import annotations

import subprocess
from typing import Any

import pytz
import requests

from app import IPINFO_URL

# Common Olson → Windows timezone map (extend as needed)
OLSON_TO_WINDOWS: dict[str, str] = {
    "America/Los_Angeles": "Pacific Standard Time",
    "America/Denver": "Mountain Standard Time",
    "America/Phoenix": "US Mountain Standard Time",
    "America/Chicago": "Central Standard Time",
    "America/New_York": "Eastern Standard Time",
    "America/Anchorage": "Alaskan Standard Time",
    "Pacific/Honolulu": "Hawaiian Standard Time",
    "America/Toronto": "Eastern Standard Time",
    "America/Vancouver": "Pacific Standard Time",
    "America/Edmonton": "Mountain Standard Time",
    "America/Winnipeg": "Central Standard Time",
    "UTC": "UTC",
}


def fetch_ipinfo() -> dict[str, Any]:
    response = requests.get(IPINFO_URL, timeout=20)
    response.raise_for_status()
    return response.json()


def windows_tz_for_olson(olson: str) -> str | None:
    if olson in OLSON_TO_WINDOWS:
        return OLSON_TO_WINDOWS[olson]
    # validate olson exists
    try:
        pytz.timezone(olson)
    except Exception:  # noqa: BLE001
        return None
    return OLSON_TO_WINDOWS.get(olson)


def apply_windows_timezone(windows_name: str) -> None:
    subprocess.run(
        ["tzutil", "/s", windows_name],
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def sync_timezone_from_ip() -> str:
    info = fetch_ipinfo()
    olson = str(info.get("timezone") or "")
    windows = windows_tz_for_olson(olson)
    if not windows:
        # recovered client defaulted toward Pacific in UI strings
        windows = "Pacific Standard Time"
    apply_windows_timezone(windows)
    return windows
