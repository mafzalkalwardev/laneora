"""How many DAT search tabs this login may open. No server imports."""
from __future__ import annotations

from typing import Any

MAX_SEARCH_TABS = 2


def entitled_search_tabs(payload: dict[str, Any] | None) -> int:
    """Old authenticate payloads omit max_searches and stay one tab."""
    if not isinstance(payload, dict):
        return 1
    try:
        count = int(payload.get("max_searches", 1))
    except (TypeError, ValueError):
        return 1
    if count >= MAX_SEARCH_TABS:
        return MAX_SEARCH_TABS
    if count == 1:
        return 1
    return 1


def can_open_another_search(open_tabs: int, entitled: int) -> bool:
    if entitled < MAX_SEARCH_TABS:
        return False
    return open_tabs < entitled and open_tabs < MAX_SEARCH_TABS
