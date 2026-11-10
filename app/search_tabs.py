"""How many DAT search tabs this login may open. No server imports."""
from __future__ import annotations

from typing import Any

ALLOWED_SEARCH_TIERS = (1, 2, 3, 6)
MAX_SEARCH_TABS = 6


def entitled_search_tabs(payload: dict[str, Any] | None) -> int:
    """Old authenticate payloads omit max_searches and stay one tab.

    Only 1, 2, 3, and 6 are real tiers. Any other number stays one tab.
    """
    if not isinstance(payload, dict):
        return 1
    try:
        count = int(payload.get("max_searches", 1))
    except (TypeError, ValueError):
        return 1
    if count in ALLOWED_SEARCH_TIERS:
        return count
    return 1


def can_open_another_search(open_tabs: int, entitled: int) -> bool:
    cap = entitled if entitled in ALLOWED_SEARCH_TIERS else 1
    if cap <= 1:
        return False
    return 0 <= open_tabs < cap


def switch_keeps_tabs(open_tabs: int, current: int, target: int) -> tuple[int, int]:
    """Changing tabs does not close the others. An invalid index stays put."""
    if open_tabs < 1 or not 0 <= target < open_tabs:
        return open_tabs, current
    return open_tabs, target
