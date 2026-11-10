"""Admin helpers for Soft shim: shared proxy IP, multi-PC, DAT session import."""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.config import data_dir, local_users_file, soft_config_file, write_private
from app.roster import load_roster, save_roster
from server import security
from server.subscriptions import (
    account_status,
    apply_plan,
    get_plan,
    remaining_seconds,
)

_WRITE_LOCK = threading.RLock()

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
    path = soft_config_file()
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return deepcopy(DEFAULT_CONFIG)
    out = deepcopy(DEFAULT_CONFIG)
    out.update({k: v for k, v in data.items() if k != "shared_proxy"})
    proxy = dict(DEFAULT_CONFIG["shared_proxy"])
    proxy.update(data.get("shared_proxy") or {})
    out["shared_proxy"] = proxy
    return out


def save_config(cfg: dict[str, Any]) -> None:
    write_private(soft_config_file(), json.dumps(cfg, indent=2) + "\n")


def load_local_users() -> list[dict[str, Any]]:
    path = local_users_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return list(data.get("users") or [])


def save_local_users(users: list[dict[str, Any]]) -> None:
    write_private(local_users_file(), json.dumps({"users": users}, indent=2) + "\n")


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
    password = _validate_password(password)
    streams = streams or ["one", "power"]
    users = load_local_users()
    cfg = load_config()
    password_hash = security.hash_client_password(password)
    for user in users:
        if str(user.get("username", "")).lower() == username.lower():
            user["username"] = username
            user["password_hash"] = password_hash
            user.pop("password", None)
            user["active"] = active
            user["active_subs"] = streams
            if not user.get("streams"):
                user["streams"] = _streams_for_names(streams)
            apply_shared_proxy_to_user(user, cfg)
            save_local_users(users)
            return user
    user = {
        "username": username,
        "password_hash": password_hash,
        "active": active,
        "active_subs": streams,
        "streams": _streams_for_names(streams),
    }
    apply_shared_proxy_to_user(user, cfg)
    users.append(user)
    save_local_users(users)
    return user


def set_shared_proxy(host: str, port: str | int, username: str = "", password: str = "") -> dict[str, Any]:
    with _WRITE_LOCK:
        return _set_shared_proxy(host, port, username, password)


def _set_shared_proxy(host: str, port: str | int, username: str = "", password: str = "") -> dict[str, Any]:
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
    with _WRITE_LOCK:
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
    shown = dict(proxy)
    if shown.get("pd"):
        shown["pd"] = "set"
    if shown.get("pu"):
        shown["pu"] = "set"
    return {
        "egress_ip": data.get("ip"),
        "city": data.get("city"),
        "region": data.get("region"),
        "country": data.get("country"),
        "org": data.get("org"),
        "proxy": shown,
        "raw": data,
    }


def dashboard_public_state(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg if cfg is not None else load_config()
    dash = dict(cfg.get("dashboard") or {})
    return {
        "configured": security.dashboard_configured(cfg),
        "username": str(dash.get("username") or ""),
        "totp_enabled": security.totp_is_enabled(cfg),
    }


def _cookie_count(user: dict[str, Any]) -> int:
    streams = user.get("streams") or {}
    one = streams.get("one") or {}
    store = one.get("store") or []
    return len(store) if isinstance(store, list) else 0


def public_account(user: dict[str, Any]) -> dict[str, Any]:
    status = account_status(user)
    has_password = security.is_password_hash(str(user.get("password_hash") or ""))
    one_store = ((user.get("streams") or {}).get("one") or {}).get("store") or []
    return {
        "username": user.get("username"),
        "has_password": has_password,
        "active": user.get("active", True) is not False,
        "plan": user.get("plan") or "",
        "plan_label": user.get("plan_label") or "",
        "subscription_start": user.get("subscription_start") or "",
        "subscription_end": user.get("subscription_end") or "",
        "status": status,
        "remaining_seconds": remaining_seconds(user),
        "cookies": _cookie_count(user),
        "dat_session": dat_session_summary(one_store if isinstance(one_store, list) else []),
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
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password) > 200:
        raise ValueError("Password is too long.")
    return password


def _expiry_unix(value: Any) -> float | None:
    """Cookie expiry as unix seconds. Session cookies and junk are unknown, not expired."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 10_000_000_000:
        number /= 1000.0
    return number


def _iso_utc(moment: float | None) -> str:
    if moment is None:
        return ""
    return datetime.fromtimestamp(moment, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _named_cookie_expiry(store: list[Any], name: str) -> tuple[str, float | None]:
    """Return missing, unknown, valid, or expired for one cookie name. No cookie values."""
    found = False
    latest: float | None = None
    for cookie in store:
        if not isinstance(cookie, dict) or str(cookie.get("name") or "") != name:
            continue
        found = True
        expiry = _expiry_unix(cookie.get("expirationDate"))
        if expiry is not None and (latest is None or expiry > latest):
            latest = expiry
    if not found:
        return "missing", None
    if latest is None:
        return "unknown", None
    return "present", latest


def dat_session_summary(store: list[Any] | None, now: float | None = None) -> dict[str, Any]:
    """Counts and expiry only. Safe to print and to return from the admin API."""
    cookies = [cookie for cookie in (store or []) if isinstance(cookie, dict)]
    now = time.time() if now is None else float(now)
    auth_state, auth_exp = _named_cookie_expiry(cookies, "auth0")
    cf_state, cf_exp = _named_cookie_expiry(cookies, "__cf_bm")

    def classify(state: str, expiry: float | None) -> str:
        if state != "present":
            return state
        if expiry is None:
            return "unknown"
        return "valid" if expiry > now else "expired"

    return {
        "cookies": len(cookies),
        "auth0": classify(auth_state, auth_exp),
        "auth0_expires": _iso_utc(auth_exp),
        "cf_bm": classify(cf_state, cf_exp),
        "cf_bm_expires": _iso_utc(cf_exp),
    }


def format_dat_session(summary: dict[str, Any]) -> str:
    auth = str(summary.get("auth0") or "missing")
    when = str(summary.get("auth0_expires") or "")
    cf = str(summary.get("cf_bm") or "missing")
    clock = f" until {when}" if auth == "valid" and when else (f" at {when}" if auth == "expired" and when else "")
    return f"cookies={summary.get('cookies', 0)} auth0={auth}{clock} cf_bm={cf}"


def _stream_from_capture(data: dict[str, Any] | list[Any]) -> dict[str, Any] | None:
    if isinstance(data, list):
        store, lst, sst, url = data, "{}", "", "https://one.dat.com"
    elif isinstance(data, dict):
        store = data.get("store") or data.get("cookies") or []
        lst = data.get("lst", "{}")
        sst = data.get("sst", "")
        url = data.get("url") or "https://one.dat.com"
    else:
        return None
    if not isinstance(store, list) or not store:
        return None
    return {
        "url": str(url),
        "store": store,
        "lst": lst if isinstance(lst, str) else json.dumps(lst),
        "sst": str(sst or ""),
    }


def _jar_rank(store: list[Any], now: float) -> tuple[int, float]:
    """Prefer a live auth0 over a stale capture file. __cf_bm does not decide."""
    state, expiry = _named_cookie_expiry(store, "auth0")
    if state == "missing":
        tier = 0
        stamp = 0.0
    elif state == "unknown" or expiry is None:
        tier = 2
        stamp = 0.0
    elif expiry > now:
        tier = 3
        stamp = expiry
    else:
        tier = 1
        stamp = expiry
    if tier == 0:
        latest = 0.0
        for cookie in store:
            if not isinstance(cookie, dict):
                continue
            moment = _expiry_unix(cookie.get("expirationDate"))
            if moment is not None and moment > latest:
                latest = moment
        stamp = latest
    return tier, stamp


def choose_dat_streams(
    users: list[dict[str, Any]],
    capture: dict[str, Any] | list[Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Pick the freshest DAT One jar from the capture file and existing accounts.

    A nonempty capture file does not win when another account has a later auth0.
    The returned streams are the copy a new account should store.
    """
    now = time.time() if now is None else float(now)
    best_rank: tuple[int, float, int] | None = None
    best_streams: dict[str, Any] | None = None

    def consider(streams: dict[str, Any], tie: int) -> None:
        nonlocal best_rank, best_streams
        one = streams.get("one") or {}
        store = one.get("store") or []
        if not isinstance(store, list) or not store:
            return
        rank = (*_jar_rank(store, now), tie)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_streams = streams

    captured = _stream_from_capture(capture) if capture is not None else None
    if captured is not None:
        power = deepcopy(captured)
        power["url"] = "https://power.dat.com"
        consider({"one": captured, "power": power}, 1)
    for user in users:
        streams = user.get("streams") or {}
        if isinstance(streams, dict):
            consider(streams, 0)
    if best_streams is None:
        return {name: deepcopy(blob) for name, blob in DEFAULT_STREAMS.items()}
    chosen = deepcopy(best_streams)
    one = dict(chosen.get("one") or DEFAULT_STREAMS["one"])
    if not one.get("store"):
        return {name: deepcopy(blob) for name, blob in DEFAULT_STREAMS.items()}
    power = dict(chosen.get("power") or {})
    if not power.get("store"):
        power = deepcopy(one)
        power["url"] = "https://power.dat.com"
    chosen["one"] = one
    chosen["power"] = power
    return chosen


def load_captured_dat() -> dict[str, Any] | list[Any] | None:
    path = data_dir() / "dat_cookies_captured.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, (dict, list)):
        return data
    return None


def capture_session_summary(now: float | None = None) -> dict[str, Any]:
    path = data_dir() / "dat_cookies_captured.json"
    summary = dat_session_summary([], now)
    summary["file"] = "missing"
    summary["file_mtime"] = ""
    if not path.exists():
        return summary
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    data = load_captured_dat()
    stream = _stream_from_capture(data) if data is not None else None
    store = (stream or {}).get("store") or []
    summary = dat_session_summary(store if isinstance(store, list) else [], now)
    summary["file"] = "present"
    summary["file_mtime"] = _iso_utc(mtime)
    return summary


CAPTURE_CHECK_HOURS = 12


def capture_refresh_due(now: float | None = None) -> dict[str, Any]:
    """True only when the stored auth0 is missing or already expired.

    A still-valid jar is not a reason to open Chrome. The 12 hour figure is
    how often an operator should run this check, not a forced recapture.
    """
    summary = capture_session_summary(now)
    state = str(summary.get("auth0") or "missing")
    due = summary.get("file") != "present" or state in {"missing", "expired"}
    summary["due"] = due
    summary["check_hours"] = CAPTURE_CHECK_HOURS
    return summary


def _streams_for_new_user() -> dict[str, Any]:
    """Copy the freshest DAT jar, not whatever happens to sit in the capture file."""
    return choose_dat_streams(load_local_users(), load_captured_dat())


def _streams_for_names(names: list[str]) -> dict[str, Any]:
    chosen = _streams_for_new_user()
    out: dict[str, Any] = {}
    for name in names:
        if name in chosen:
            out[name] = deepcopy(chosen[name])
        else:
            out[name] = deepcopy(DEFAULT_STREAMS.get(name, DEFAULT_STREAMS["one"]))
    return out


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
            "password_hash": security.hash_client_password(password),
            "active": True,
            "active_subs": ["one", "power"],
            "streams": _streams_for_new_user(),
        }
        apply_plan(user, plan_id, extend=False)
        apply_shared_proxy_to_user(user, load_config())
        users.append(user)
        save_local_users(users)
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
            target["password_hash"] = security.hash_client_password(password)
            target.pop("password", None)
        if plan_id:
            apply_plan(target, plan_id, extend=extend)
        if active is not None and not plan_id:
            target["active"] = bool(active)
        save_local_users(users)
        snapshot = public_account(target)
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


def _chmod_secret_files() -> None:
    for path in (soft_config_file(), local_users_file()):
        if path.exists():
            security.chmod_private(path)


def migrate_secrets() -> dict[str, Any]:
    """Hash plaintext dashboard and client passwords. Does not print secrets.

    Accounts that exist only in the desktop roster are not imported. Review them
    with import_roster() so a demo roster cannot become a server login by surprise.
    """
    with _WRITE_LOCK:
        cfg = load_config()
        dash_stats = security.migrate_dashboard_secrets(cfg)
        users = load_local_users()
        hashed = 0
        for user in users:
            if security.migrate_client_password(user):
                hashed += 1
        save_config(cfg)
        save_local_users(users)
        _chmod_secret_files()
        return {
            "dashboard_configured": security.dashboard_configured(cfg),
            "dashboard_password_hashed": bool(dash_stats["hashed"]),
            "dashboard_default_removed": bool(dash_stats["removed_default"]),
            "client_passwords_hashed": hashed,
            "session_key": security.valid_session_key(str(cfg.get("session_key") or "")),
        }


def roster_only_usernames() -> list[str]:
    existing = {str(user.get("username", "")).strip().lower() for user in load_local_users()}
    names: list[str] = []
    for entry in load_roster():
        name = str(entry.get("username") or "").strip()
        if name and name.lower() not in existing:
            names.append(name)
    return names


def import_roster(*, apply: bool) -> dict[str, Any]:
    """Copy desktop-roster accounts that are missing from the server store.

    Passwords are hashed and never returned. ``apply`` False only lists usernames.
    """
    with _WRITE_LOCK:
        users = load_local_users()
        existing = {str(user.get("username", "")).strip().lower() for user in users}
        pending: list[str] = []
        imported: list[str] = []
        cfg = load_config()
        for entry in load_roster():
            name = str(entry.get("username") or "").strip()
            password = str(entry.get("password") or "")
            if not name or name.lower() in existing:
                continue
            if not password or security.is_password_hash(password):
                continue
            pending.append(name)
            if not apply:
                continue
            user: dict[str, Any] = {
                "username": name,
                "password_hash": security.hash_client_password(password),
                "active": True,
                "active_subs": ["one", "power"],
                "streams": {stream: deepcopy(DEFAULT_STREAMS[stream]) for stream in ("one", "power")},
            }
            apply_shared_proxy_to_user(user, cfg)
            users.append(user)
            existing.add(name.lower())
            imported.append(name)
        if imported:
            save_local_users(users)
        return {"pending": pending, "imported": imported}


def strip_roster_passwords() -> int:
    """Blank desktop-roster passwords. Server logins are unchanged."""
    users = load_roster()
    for user in users:
        user["password"] = ""
    save_roster(users)
    return len(users)


def _require_session_key(cfg: dict[str, Any]) -> None:
    if not security.valid_session_key(str(cfg.get("session_key") or "")):
        security.migrate_dashboard_secrets(cfg)


def current_session(token: str | None) -> str | None:
    if not token:
        return None
    cfg = load_config()
    payload = security.parse_session(cfg, token)
    if payload is None:
        return None
    return str(payload["username"])


def revoke_presented_session(token: str | None) -> None:
    if not token:
        return
    with _WRITE_LOCK:
        cfg = load_config()
        payload = security.parse_session(cfg, token)
        if payload is None:
            return
        security.revoke_session_id(cfg, str(payload["sid"]))
        save_config(cfg)


def revoke_all_sessions() -> int:
    with _WRITE_LOCK:
        cfg = load_config()
        _require_session_key(cfg)
        generation = security.bump_session_generation(cfg)
        save_config(cfg)
        return generation


def login_dashboard(username: str, password: str, code: str = "") -> dict[str, Any]:
    """Return status ok, totp, or fail. The token is only present on full success."""
    with _WRITE_LOCK:
        cfg = load_config()
        _require_session_key(cfg)
        if not security.dashboard_password_ok(cfg, username.strip(), str(password or "").strip()):
            save_config(cfg)
            return {"status": "fail"}
        if security.totp_is_enabled(cfg):
            totp = security.totp_record(cfg)
            presented = code or ""
            if not presented.strip():
                save_config(cfg)
                return {"status": "totp"}
            step = security.matching_totp_step(
                str(totp.get("secret") or ""),
                presented,
                int(totp.get("last_step") or 0),
            )
            if step is not None:
                totp["last_step"] = step
            else:
                hashes = [str(item) for item in (totp.get("recovery_hashes") or [])]
                kept = security.consume_recovery_code(presented, hashes)
                if kept is None:
                    save_config(cfg)
                    return {"status": "fail"}
                totp["recovery_hashes"] = kept
            dash = cfg["dashboard"]
            token = security.issue_session(cfg, str(dash.get("username") or ""))
            save_config(cfg)
            return {"status": "ok", "token": token, "username": dash.get("username")}
        dash = cfg["dashboard"]
        token = security.issue_session(cfg, str(dash.get("username") or ""))
        save_config(cfg)
        return {"status": "ok", "token": token, "username": dash.get("username")}


def change_dashboard_credentials(
    current_password: str,
    new_password: str | None = None,
    new_username: str | None = None,
) -> str:
    """Require the current password, then revoke every session and issue a new one."""
    with _WRITE_LOCK:
        cfg = load_config()
        dash = dict(cfg.get("dashboard") or {})
        username = str(dash.get("username") or "")
        if not security.dashboard_password_ok(cfg, username, str(current_password or "").strip()):
            raise ValueError("Current dashboard password is wrong.")
        if new_username:
            username = security.validate_dashboard_username(new_username)
            dash["username"] = username
        if new_password:
            dash["password_hash"] = security.hash_password(
                security.validate_dashboard_password(new_password, username)
            )
            dash.pop("password", None)
            dash["defaults_screened"] = True
        if not new_username and not new_password:
            raise ValueError("Provide a new username or a new password.")
        cfg["dashboard"] = dash
        _require_session_key(cfg)
        security.bump_session_generation(cfg)
        token = security.issue_session(cfg, username)
        save_config(cfg)
        return token


def replace_dashboard_credentials(
    username: str | None,
    password: str | None,
    *,
    generate_username: bool = False,
    generate_password: bool = False,
) -> dict[str, str]:
    """Local-operator break-glass. Returns generated secrets once; stores only a hash."""
    with _WRITE_LOCK:
        cfg = load_config()
        _require_session_key(cfg)
        dash = dict(cfg.get("dashboard") or {})
        generated: dict[str, str] = {}
        current_name = str(dash.get("username") or "").strip()
        if generate_username or not (username or current_name):
            username = secrets.token_hex(16)
            generated["username"] = username
            username = security.validate_dashboard_username(username)
        elif username:
            username = security.validate_dashboard_username(username)
        else:
            # Keep an already-configured name so a password rotation cannot lock
            # the owner out for failing a new-username rule.
            username = current_name
        if not username:
            raise ValueError("Dashboard username is missing.")
        if generate_password or not password:
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
            password = "".join(secrets.choice(alphabet) for _ in range(40))
            generated["password"] = password
        password = security.validate_dashboard_password(password, username)
        dash["username"] = username
        dash["password_hash"] = security.hash_password(password)
        dash.pop("password", None)
        dash.pop("password_removed", None)
        dash["defaults_screened"] = True
        cfg["dashboard"] = dash
        security.bump_session_generation(cfg)
        save_config(cfg)
        generated["username_set"] = username
        return generated


def begin_totp() -> dict[str, str]:
    with _WRITE_LOCK:
        cfg = load_config()
        if not security.dashboard_configured(cfg):
            raise ValueError("Set a dashboard login before turning on two-factor authentication.")
        if security.totp_is_enabled(cfg):
            raise ValueError("Two-factor authentication is already on.")
        dash = cfg["dashboard"]
        secret = security.new_totp_secret()
        totp = security.totp_record(cfg)
        totp["pending_secret"] = secret
        totp["enabled"] = False
        save_config(cfg)
        username = str(dash.get("username") or "")
        return {"secret": secret, "otpauth": security.totp_uri(secret, username)}


def confirm_totp(code: str) -> tuple[list[str], str]:
    with _WRITE_LOCK:
        cfg = load_config()
        totp = security.totp_record(cfg)
        pending = str(totp.get("pending_secret") or "")
        step = security.matching_totp_step(pending, code, 0)
        if step is None:
            raise ValueError("That verification code did not match.")
        plain, hashed = security.new_recovery_codes()
        totp["secret"] = pending
        totp["pending_secret"] = ""
        totp["enabled"] = True
        totp["last_step"] = step
        totp["recovery_hashes"] = hashed
        security.bump_session_generation(cfg)
        username = str(cfg["dashboard"].get("username") or "")
        token = security.issue_session(cfg, username)
        save_config(cfg)
        return plain, token


def disable_totp(password: str, code: str, *, lost_device: bool = False) -> str:
    with _WRITE_LOCK:
        cfg = load_config()
        dash = cfg.get("dashboard") or {}
        username = str(dash.get("username") or "")
        if not security.dashboard_password_ok(cfg, username, str(password or "").strip()):
            raise ValueError("Current dashboard password is wrong.")
        totp = security.totp_record(cfg)
        if security.totp_is_enabled(cfg) and not lost_device:
            step = security.matching_totp_step(str(totp.get("secret") or ""), code, int(totp.get("last_step") or 0))
            hashes = [str(item) for item in (totp.get("recovery_hashes") or [])]
            kept = None if step is not None else security.consume_recovery_code(code, hashes)
            if step is None and kept is None:
                raise ValueError("That verification code did not match.")
        cfg["dashboard"]["totp"] = {"enabled": False, "secret": "", "pending_secret": "", "recovery_hashes": [], "last_step": 0}
        security.bump_session_generation(cfg)
        token = security.issue_session(cfg, username)
        save_config(cfg)
        return token


def prepare_server() -> dict[str, Any]:
    os.umask(0o077)
    return migrate_secrets()
