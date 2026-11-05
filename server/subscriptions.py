"""Subscription plans and login checks for Soft accounts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Fixed lengths so the end time is predictable from the moment a plan is applied.
PLANS: list[dict[str, Any]] = [
    {"id": "trial_1h", "label": "Trial — 1 hour", "delta": timedelta(hours=1)},
    {"id": "day_1", "label": "1 day", "delta": timedelta(days=1)},
    {"id": "week_1", "label": "1 week", "delta": timedelta(days=7)},
    {"id": "days_15", "label": "15 days", "delta": timedelta(days=15)},
    {"id": "month_1", "label": "1 month", "delta": timedelta(days=30)},
    {"id": "months_3", "label": "3 months", "delta": timedelta(days=90)},
    {"id": "months_6", "label": "6 months", "delta": timedelta(days=180)},
    {"id": "year_1", "label": "1 year", "delta": timedelta(days=365)},
]

_BY_ID = {plan["id"]: plan for plan in PLANS}


def plan_catalog() -> list[dict[str, str]]:
    return [{"id": plan["id"], "label": plan["label"]} for plan in PLANS]


def get_plan(plan_id: str) -> dict[str, Any]:
    plan = _BY_ID.get((plan_id or "").strip())
    if plan is None:
        known = ", ".join(plan["id"] for plan in PLANS)
        raise ValueError(f"Unknown plan '{plan_id}'. Use one of: {known}")
    return plan


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_utc(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def format_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def account_status(user: dict[str, Any], now: datetime | None = None) -> str:
    """active, expired, disabled, or unset (no plan yet — login still allowed)."""
    if user.get("active", True) is False:
        return "disabled"
    end = parse_utc(user.get("subscription_end"))
    if end is None:
        return "unset"
    now = now or utc_now()
    if end <= now:
        return "expired"
    return "active"


def remaining_seconds(user: dict[str, Any], now: datetime | None = None) -> int | None:
    end = parse_utc(user.get("subscription_end"))
    if end is None:
        return None
    now = now or utc_now()
    return int((end - now).total_seconds())


def denial_payload(user: dict[str, Any], now: datetime | None = None) -> dict[str, str] | None:
    """JSON body for /authenticate when this account must not log in."""
    status = account_status(user, now)
    if status == "disabled":
        return {
            "status": "disabled",
            "message": "This account is disabled. Ask your admin.",
        }
    if status == "expired":
        label = str(user.get("plan_label") or "Subscription")
        end = str(user.get("subscription_end") or "")
        return {
            "status": "expired",
            "message": f"{label} ended {end}. Ask your admin to renew.",
        }
    return None


def apply_plan(user: dict[str, Any], plan_id: str, *, extend: bool = False, now: datetime | None = None) -> dict[str, Any]:
    plan = get_plan(plan_id)
    now = now or utc_now()
    current_end = parse_utc(user.get("subscription_end"))
    if extend and current_end is not None and current_end > now:
        start = parse_utc(user.get("subscription_start")) or now
        end = current_end + plan["delta"]
    else:
        start = now
        end = now + plan["delta"]
    user["plan"] = plan["id"]
    user["plan_label"] = plan["label"]
    user["subscription_start"] = format_utc(start)
    user["subscription_end"] = format_utc(end)
    user["active"] = True
    return user
