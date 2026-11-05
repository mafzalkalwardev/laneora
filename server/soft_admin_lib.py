"""Admin helpers for Soft shim: shared proxy IP, multi-PC, DAT session import."""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, LOCAL_USERS_FILE, SOFT_CONFIG_FILE
from app.roster import load_roster, save_roster, upsert_user
from server.subscriptions import (
    account_status,
    apply_plan,
    get_plan,
    remaining_seconds,
)

_WRITE_LOCK = threading.Lock()
_CAPTURED_COOKIES = DATA_DIR / "dat_cookies_captured.json"

DEFAULT_STREAMS = {
    "one": {"url": "https://one.dat.com", "store": [], "lst": "{}", "sst": ""},
    "power": {"url": "https://power.dat.com", "store": [], "lst": "{}", "sst": ""},
}

DEFAULT_CONFIG = {
    "allow_multi_screen": True,
    "note": "All PCs must use the same shared HTTP proxy so DAT owners see one egress IP.",
    "shared_proxy": {"px": "none", "p": "0", "pu": "", "pd": ""},
}


def load_config() -> dict[str, Any]:
    if not SOFT_CONFIG_FILE.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        data = json.loads(SOFT_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_CONFIG)
    out = deepcopy(DEFAULT_CONFIG)
    out.update({k: v for k, v in data.items() if k != "shared_proxy"})
    proxy = dict(DEFAULT_CONFIG["shared_proxy"])
    proxy.update(data.get("shared_proxy") or {})
    out["shared_proxy"] = proxy
    return out


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_config(cfg: dict[str, Any]) -> None:
    _atomic_write(SOFT_CONFIG_FILE, json.dumps(cfg, indent=2) + "\n")


def load_local_users() -> list[dict[str, Any]]:
    if not LOCAL_USERS_FILE.exists():
        return []
    try:
        data = json.loads(LOCAL_USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("users") or [])


def save_local_users(users: list[dict[str, Any]]) -> None:
    _atomic_write(LOCAL_USERS_FILE, json.dumps({"users": users}, indent=2) + "\n")


def apply_shared_proxy_to_user(user: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    proxy = cfg.get("shared_proxy") or {}
    px = str(proxy.get("px") or "none")
    # Per-user override wins only if explicitly set and shared is none? No — shared wins for same-IP goal.
    if px and px.lower() not in ("", "none"):
        user["px"] = px
        user["p"] = str(proxy.get("p") or "0")
        user["pu"] = str(proxy.get("pu") or "")
        user["pd"] = str(proxy.get("pd") or "")
    elif "px" not in user:
        user["px"] = "none"
        user["p"] = "0"
        user["pu"] = ""
        user["pd"] = ""
    return user


def upsert_account(
    username: str,
    password: str,
    *,
    streams: list[str] | None = None,
    active: bool = True,
) -> dict[str, Any]:
    username = username.strip()
    password = password.strip()
    streams = streams or ["one", "power"]
    users = load_local_users()
    cfg = load_config()
    for user in users:
        if str(user.get("username", "")).lower() == username.lower():
            user["username"] = username
            user["password"] = password
            user["active"] = active
            user["active_subs"] = streams
            if not user.get("streams"):
                user["streams"] = {name: deepcopy(DEFAULT_STREAMS.get(name, DEFAULT_STREAMS["one"])) for name in streams}
            apply_shared_proxy_to_user(user, cfg)
            save_local_users(users)
            return user
    user = {
        "username": username,
        "password": password,
        "active": active,
        "active_subs": streams,
        "streams": {name: deepcopy(DEFAULT_STREAMS.get(name, DEFAULT_STREAMS["one"])) for name in streams},
    }
    apply_shared_proxy_to_user(user, cfg)
    users.append(user)
    save_local_users(users)
    return user


def set_shared_proxy(host: str, port: str | int, username: str = "", password: str = "") -> dict[str, Any]:
    cfg = load_config()
    cfg["shared_proxy"] = {
        "px": host.strip() or "none",
        "p": str(port or "0"),
        "pu": username or "",
        "pd": password or "",
    }
    save_config(cfg)
    # Propagate to every Soft account so all PCs get the same egress IP
    users = load_local_users()
    for user in users:
        apply_shared_proxy_to_user(user, cfg)
    save_local_users(users)
    return cfg


def set_multi_screen(allow: bool) -> dict[str, Any]:
    cfg = load_config()
    cfg["allow_multi_screen"] = bool(allow)
    save_config(cfg)
    return cfg


def import_dat_store(
    soft_username: str,
    stream: str,
    store: list[dict[str, Any]],
    *,
    lst: str = "{}",
    sst: str = "",
    url: str | None = None,
) -> dict[str, Any]:
    """Attach a DAT cookie jar to a Soft user's stream (shared across all PCs)."""
    soft_username = soft_username.strip()
    stream = stream.strip().lower() or "one"
    users = load_local_users()
    cfg = load_config()
    target = None
    for user in users:
        if str(user.get("username", "")).lower() == soft_username.lower():
            target = user
            break
    if target is None:
        raise ValueError(f"Soft user '{soft_username}' not found — create with soft_admin add-user first")
    streams = dict(target.get("streams") or {})
    base = deepcopy(streams.get(stream) or DEFAULT_STREAMS.get(stream) or DEFAULT_STREAMS["one"])
    base["store"] = store
    base["lst"] = lst if isinstance(lst, str) else json.dumps(lst)
    base["sst"] = sst
    if url:
        base["url"] = url
    streams[stream] = base
    target["streams"] = streams
    subs = list(target.get("active_subs") or [])
    if stream not in subs:
        subs.append(stream)
        target["active_subs"] = subs
    apply_shared_proxy_to_user(target, cfg)
    save_local_users(users)
    return target


def check_egress_ip(timeout: float = 25.0) -> dict[str, Any]:
    """Hit ipinfo through the shared proxy — what DAT owners would see."""
    import requests

    cfg = load_config()
    proxy = cfg.get("shared_proxy") or {}
    host = str(proxy.get("px") or "none")
    proxies = None
    if host.lower() not in ("", "none", "direct", "local"):
        user = str(proxy.get("pu") or "")
        pwd = str(proxy.get("pd") or "")
        port = str(proxy.get("p") or "0")
        auth = f"{user}:{pwd}@" if user or pwd else ""
        proxies = {
            "http": f"http://{auth}{host}:{port}",
            "https": f"http://{auth}{host}:{port}",
        }
    r = requests.get("https://ipinfo.io/json", proxies=proxies, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return {
        "egress_ip": data.get("ip"),
        "city": data.get("city"),
        "region": data.get("region"),
        "country": data.get("country"),
        "org": data.get("org"),
        "proxy": proxy,
        "raw": data,
    }


def ensure_dashboard_login() -> dict[str, str]:
    """Dashboard login is separate from Soft client accounts. Seed once."""
    with _WRITE_LOCK:
        cfg = load_config()
        dash = dict(cfg.get("dashboard") or {})
        username = str(dash.get("username") or "").strip() or "admin"
        password = str(dash.get("password") or "")
        if not password:
            password = "admin123"
        dash["username"] = username
        dash["password"] = password
        cfg["dashboard"] = dash
        save_config(cfg)
        return {"username": username, "password": password}


def dashboard_login() -> dict[str, str]:
    cfg = load_config()
    dash = dict(cfg.get("dashboard") or {})
    if not dash.get("username") or not dash.get("password"):
        return ensure_dashboard_login()
    return {"username": str(dash["username"]), "password": str(dash["password"])}


def set_dashboard_password(current: str, new_password: str) -> None:
    new_password = new_password.strip()
    if len(new_password) < 4:
        raise ValueError("Dashboard password must be at least 4 characters.")
    with _WRITE_LOCK:
        cfg = load_config()
        dash = dict(cfg.get("dashboard") or {})
        if str(dash.get("password") or "") != current:
            raise ValueError("Current dashboard password is wrong.")
        dash["username"] = str(dash.get("username") or "admin")
        dash["password"] = new_password
        cfg["dashboard"] = dash
        save_config(cfg)


def _cookie_count(user: dict[str, Any]) -> int:
    streams = user.get("streams") or {}
    one = streams.get("one") or {}
    store = one.get("store") or []
    return len(store) if isinstance(store, list) else 0


def public_account(user: dict[str, Any]) -> dict[str, Any]:
    status = account_status(user)
    return {
        "username": user.get("username"),
        "password": user.get("password"),
        "active": user.get("active", True) is not False,
        "plan": user.get("plan") or "",
        "plan_label": user.get("plan_label") or "",
        "subscription_start": user.get("subscription_start") or "",
        "subscription_end": user.get("subscription_end") or "",
        "status": status,
        "remaining_seconds": remaining_seconds(user),
        "cookies": _cookie_count(user),
    }


def list_accounts() -> list[dict[str, Any]]:
    return [public_account(user) for user in load_local_users()]


def _validate_username(username: str) -> str:
    username = username.strip()
    if len(username) < 3 or len(username) > 32:
        raise ValueError("Username must be 3–32 characters.")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(ch not in allowed for ch in username):
        raise ValueError("Username can use letters, numbers, _ and - only.")
    return username


def _validate_password(password: str) -> str:
    password = password.strip()
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")
    return password


def _streams_for_new_user() -> dict[str, Any]:
    """Give a new Soft user the captured DAT session, or copy one that already has cookies."""
    if _CAPTURED_COOKIES.exists():
        try:
            data = json.loads(_CAPTURED_COOKIES.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        store = data.get("store") or data.get("cookies") or []
        if isinstance(store, list) and store:
            one = {
                "url": data.get("url") or "https://one.dat.com",
                "store": store,
                "lst": str(data.get("lst", "{}")),
                "sst": str(data.get("sst", "")),
            }
            power = deepcopy(one)
            power["url"] = "https://power.dat.com"
            return {"one": one, "power": power}
    for user in load_local_users():
        streams = user.get("streams") or {}
        store = (streams.get("one") or {}).get("store") or []
        if store:
            return deepcopy(streams)
    return {name: deepcopy(blob) for name, blob in DEFAULT_STREAMS.items()}


def _sync_roster(username: str, password: str) -> None:
    upsert_user(username, password)


def _drop_roster(username: str) -> None:
    kept = [user for user in load_roster() if user["username"].lower() != username.lower()]
    save_roster(kept)


def create_account(username: str, password: str, plan_id: str) -> dict[str, Any]:
    username = _validate_username(username)
    password = _validate_password(password)
    get_plan(plan_id)
    with _WRITE_LOCK:
        users = load_local_users()
        for user in users:
            if str(user.get("username", "")).lower() == username.lower():
                raise ValueError(f"User '{username}' already exists.")
        user: dict[str, Any] = {
            "username": username,
            "password": password,
            "active": True,
            "active_subs": ["one", "power"],
            "streams": _streams_for_new_user(),
        }
        apply_plan(user, plan_id, extend=False)
        apply_shared_proxy_to_user(user, load_config())
        users.append(user)
        save_local_users(users)
    _sync_roster(username, password)
    return public_account(user)


def update_account(
    username: str,
    *,
    password: str | None = None,
    plan_id: str | None = None,
    extend: bool = False,
    active: bool | None = None,
) -> dict[str, Any]:
    username = username.strip()
    if password is not None and password != "":
        password = _validate_password(password)
    else:
        password = None
    if plan_id:
        get_plan(plan_id)
    with _WRITE_LOCK:
        users = load_local_users()
        target = None
        for user in users:
            if str(user.get("username", "")).lower() == username.lower():
                target = user
                break
        if target is None:
            raise ValueError(f"User '{username}' was not found.")
        if password is not None:
            target["password"] = password
        if plan_id:
            apply_plan(target, plan_id, extend=extend)
        if active is not None and not plan_id:
            target["active"] = bool(active)
        save_local_users(users)
        saved_password = str(target.get("password") or "")
        saved_name = str(target.get("username") or username)
        snapshot = public_account(target)
    _sync_roster(saved_name, saved_password)
    return snapshot


def delete_account(username: str) -> None:
    username = username.strip()
    with _WRITE_LOCK:
        users = load_local_users()
        kept = [user for user in users if str(user.get("username", "")).lower() != username.lower()]
        if len(kept) == len(users):
            raise ValueError(f"User '{username}' was not found.")
        save_local_users(kept)
    _drop_roster(username)
