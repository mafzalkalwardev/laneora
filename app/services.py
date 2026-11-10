"""Modules an admin can turn on per Laneora login.

`dat` is the original client: one DAT One search screen. The multi-search
modules open two, three, or six DAT search tabs. Each tab uses its own browser
profile so the searches do not share cookies, storage, or navigation. Every
tab still receives the same shared DAT session and the same proxy.

A missing or empty service list means `[dat]`. Existing accounts keep the
original module until an admin assigns something else.

Six tabs is the ceiling. Each tab is its own off-the-record Chromium profile,
so nothing is written to a profile directory. Six tabs that reached the DAT
login page used about 1.1 GB for the whole client in a local check, peaking
near 1.25 GB. A signed-in search, with the map and the load table, will use
more. Assign the six-search module only on a PC that has that memory free.
The tabs hold separate copies of the shared session, so a board that rotates
a refresh token can leave the later tabs stale. Dual DAT Search already works
this way.
"""
from __future__ import annotations

from typing import Any

from app import POWER_DAT

DAT = "dat"
DAT_DUAL = "dat_dual"
DAT_3 = "dat_3"
DAT_6 = "dat_6"

# How many isolated search tabs each multi-search module opens.
MULTI_SEARCH_TABS: dict[str, int] = {
    DAT_DUAL: 2,
    DAT_3: 3,
    DAT_6: 6,
}

ONE_SEARCH_URL = "https://one.dat.com/search-loads"

# Dual search keeps the original simultaneous open. Larger modules stagger
# later tabs so six profiles do not all parse the board at the same instant.
SEARCH_OPEN_DELAY_MS = 400
SEARCH_TAB_STAGGER_MS = 350


def search_tab_titles(count: int) -> tuple[str, ...]:
    if count < 1:
        raise ValueError("A search module needs at least one tab.")
    return tuple(f"Search {index}" for index in range(1, count + 1))


def search_open_delay_ms(index: int, count: int) -> int:
    """Milliseconds before tab `index` loads. Dual search stays at 400ms."""
    if count <= MULTI_SEARCH_TABS[DAT_DUAL]:
        return SEARCH_OPEN_DELAY_MS
    return SEARCH_OPEN_DELAY_MS + index * SEARCH_TAB_STAGGER_MS


# Tab titles for the dual-search module. Order is the order they appear in.
DUAL_SEARCH_TABS = search_tab_titles(MULTI_SEARCH_TABS[DAT_DUAL])

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
    {
        "id": DAT_3,
        "label": "3 DAT Search",
        "short": "3 Search",
        "button": "3 DAT Search",
        "description": "Three DAT search tabs. Each tab is its own search session.",
    },
    {
        "id": DAT_6,
        "label": "6 DAT Search",
        "short": "6 Search",
        "button": "6 DAT Search",
        "description": "Six DAT search tabs. Each tab is its own search session.",
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


def opens_dat_search(service_id: str) -> bool:
    """True when this module loads the shared DAT One session."""
    return service_id == DAT or service_id in MULTI_SEARCH_TABS


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
