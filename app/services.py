"""Modules an admin can turn on per Laneora login.

`dat` is the original client: one DAT One search screen. `dat_dual` opens two
DAT search tabs. Each tab uses its own browser profile so the searches do not
share cookies, storage, or navigation. Both tabs still receive the same shared
DAT session and the same proxy.

A missing or empty service list means `[dat]`. Existing accounts keep the
original module until an admin assigns something else.
"""
from __future__ import annotations

from typing import Any

from app import POWER_DAT

DAT = "dat"
DAT_DUAL = "dat_dual"

# Tab titles for the dual-search module. Order is the order they appear in.
DUAL_SEARCH_TABS = ("Search 1", "Search 2")

ONE_SEARCH_URL = "https://one.dat.com/search-loads"

SERVICES: list[dict[str, str]] = [
    {
        "id": DAT,
        "label": "DAT Search",
        "short": "DAT Search",
        "button": "Load DAT Stream",
        "description": "One DAT One search screen.",
    },
    {
        "id": DAT_DUAL,
        "label": "Dual DAT Search",
        "short": "Dual Search",
        "button": "Dual DAT Search",
        "description": "Two DAT search tabs. Each tab is its own search session.",
    },
]

_BY_ID = {service["id"]: service for service in SERVICES}


def service_catalog() -> list[dict[str, str]]:
    return [
        {"id": service["id"], "label": service["label"], "description": service["description"]}
        for service in SERVICES
    ]


def service_by_id(service_id: str) -> dict[str, str]:
    try:
        return _BY_ID[service_id]
    except KeyError as exc:
        known = ", ".join(service["id"] for service in SERVICES)
        raise ValueError(f"Unknown service '{service_id}'. Use one of: {known}") from exc


def _iter_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    raise ValueError("Services must be a list of service ids.")


def require_services(raw: Any) -> list[str]:
    """Validate an admin assignment. Unknown ids and an empty list are errors."""
    try:
        ids = _iter_ids(raw)
    except ValueError as exc:
        raise ValueError("Services must be a list of service ids.") from exc
    if not ids:
        raise ValueError("Assign at least one service.")
    unknown = [item for item in ids if item not in _BY_ID]
    if unknown:
        known = ", ".join(service["id"] for service in SERVICES)
        raise ValueError(f"Unknown service '{unknown[0]}'. Use one of: {known}")
    chosen = set(ids)
    return [service["id"] for service in SERVICES if service["id"] in chosen]


def normalize_services(raw: Any) -> list[str]:
    """Effective modules for a stored account or an auth payload.

    Missing, empty, or unrecognized values fall back to the original DAT Search
    so an old account never opens onto a blank window.
    """
    if raw is None:
        return [DAT]
    try:
        ids = _iter_ids(raw)
    except ValueError:
        return [DAT]
    chosen = set(ids)
    found = [service["id"] for service in SERVICES if service["id"] in chosen]
    return found or [DAT]


def search_url(full_make: dict[str, Any], opt: str) -> str:
    """Same DAT URL rules the original single-search tab uses."""
    if "power" in (opt or "").lower():
        return POWER_DAT
    raw = str(full_make.get("url") or "")
    if "one.dat.com" in raw:
        return ONE_SEARCH_URL
    return raw or ONE_SEARCH_URL
