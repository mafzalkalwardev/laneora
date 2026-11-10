"""
Soft admin CLI — shared egress IP, multi-PC sessions, DAT cookie import.

Examples:
  python scripts/soft_admin.py status
  python scripts/soft_admin.py multi-screen on
  python scripts/soft_admin.py set-proxy HOST PORT [USER] [PASS]
  python scripts/soft_admin.py check-ip
  python scripts/soft_admin.py add-user dispatcher3 secret123
  python scripts/soft_admin.py import-store dispatcher3 one path/to/cookies.json
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.soft_admin_lib import (  # noqa: E402
    capture_refresh_due,
    capture_session_summary,
    check_egress_ip,
    dashboard_public_state,
    dat_session_summary,
    disable_totp,
    format_dat_session,
    import_dat_store,
    import_roster,
    load_config,
    load_local_users,
    migrate_secrets,
    replace_dashboard_credentials,
    revoke_all_sessions,
    roster_only_usernames,
    set_multi_screen,
    set_shared_proxy,
    strip_roster_passwords,
    upsert_account,
    begin_totp,
    confirm_totp,
)


def _secret_from_env_or_prompt(env_name: str, prompt: str) -> str:
    value = os.environ.get(env_name, "")
    if value:
        return value
    if not sys.stdin.isatty():
        raise SystemExit(f"Set {env_name}. Passwords are not accepted as arguments.")
    return getpass.getpass(prompt)


def cmd_status(_: argparse.Namespace) -> int:
    cfg = load_config()
    users = load_local_users()
    state = dashboard_public_state(cfg)
    plain_clients = sum(1 for user in users if isinstance(user.get("password"), str) and user.get("password"))
    plain_dashboard = bool((cfg.get("dashboard") or {}).get("password"))
    print("dashboard_configured:", state["configured"] or plain_dashboard)
    print("dashboard_totp:", state["totp_enabled"])
    if plain_clients or plain_dashboard:
        print("plaintext passwords are still stored.")
        print("Snapshot data/soft_config.json and data/local_users.json, then run: python scripts/soft_admin.py migrate")
    proxy = cfg.get("shared_proxy") or {}
    print("allow_multi_screen:", cfg.get("allow_multi_screen", True))
    print(
        "shared_proxy:",
        f"{proxy.get('px')}:{proxy.get('p')}",
        f"user={proxy.get('pu') or '(none)'}",
    )
    print(f"accounts ({len(users)}):")
    for user in users:
        one = ((user.get("streams") or {}).get("one") or {}).get("store") or []
        print(
            f"  - {user.get('username')}  active={user.get('active', True)}  "
            f"plan={user.get('plan_label') or 'no plan'}  "
            f"ends={user.get('subscription_end') or '—'}  "
            f"subs={user.get('active_subs')}  px={user.get('px')}  "
            f"dat={format_dat_session(dat_session_summary(one if isinstance(one, list) else []))}"
        )
    captured = capture_session_summary()
    print(
        "captured_jar:",
        captured.get("file"),
        format_dat_session(captured),
        f"file_mtime={captured.get('file_mtime') or '—'}",
    )
    print()
    print("Same IP on every PC requires a real shared HTTP proxy (not px=none).")
    print("DAT owners see that proxy egress IP, not each PC's home IP.")
    return 0


def cmd_multi(args: argparse.Namespace) -> int:
    allow = args.mode.lower() in ("on", "1", "true", "yes")
    cfg = set_multi_screen(allow)
    print("allow_multi_screen =", cfg["allow_multi_screen"])
    if allow:
        print("Same Soft user can stay logged in on many PCs (no Multiple Screens block).")
    else:
        print("Single-screen Soft behavior: newest PC wins; others get blocked.")
    return 0


def cmd_proxy(args: argparse.Namespace) -> int:
    cfg = set_shared_proxy(args.host, args.port, args.username or "", args.password or "")
    proxy = cfg["shared_proxy"]
    print("shared_proxy saved:", proxy)
    print("Propagated to all Soft accounts in data/local_users.json")
    return 0


def cmd_check_ip(_: argparse.Namespace) -> int:
    try:
        info = check_egress_ip()
    except Exception as exc:  # noqa: BLE001
        print("Failed to check egress IP:", exc)
        print("Set a working shared proxy first: soft_admin.py set-proxy HOST PORT [USER] [PASS]")
        return 1
    print("egress_ip:", info.get("egress_ip"))
    print("city/region:", info.get("city"), info.get("region"), info.get("country"))
    print("org:", info.get("org"))
    print("via proxy:", info.get("proxy"))
    return 0


def cmd_add_user(args: argparse.Namespace) -> int:
    streams = [s.strip() for s in (args.streams or "one,power").split(",") if s.strip()]
    user = upsert_account(args.username, args.password, streams=streams)
    print("saved", user.get("username"), "subs=", user.get("active_subs"), "px=", user.get("px"))
    return 0


def cmd_capture_if_expired(_: argparse.Namespace) -> int:
    """Exit 2 when the signed-in Chrome capture should run. Exit 0 when it should not."""
    info = capture_refresh_due()
    print("check_every_hours:", info.get("check_hours"))
    print("jar", format_dat_session(info), f"file={info.get('file')}")
    if not info.get("due"):
        print("auth0 still valid. Chrome was not touched.")
        return 0
    print("auth0 is missing or expired. Use the existing signed-in Chrome on port 9334, then push-capture.")
    return 2


def cmd_push_capture(args: argparse.Namespace) -> int:
    """Push data/dat_cookies_captured.json into every Soft account (or one user)."""
    path = Path(args.file or (ROOT / "data" / "dat_cookies_captured.json"))
    if not path.exists():
        print("missing", path)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    store = data.get("store") or data.get("cookies") or []
    if isinstance(data, list):
        store = data
    lst = str(data.get("lst", "{}")) if isinstance(data, dict) else "{}"
    sst = str(data.get("sst", "")) if isinstance(data, dict) else ""
    url_one = (data.get("url") if isinstance(data, dict) else None) or "https://one.dat.com"
    summary = dat_session_summary(store if isinstance(store, list) else [])
    print("jar", format_dat_session(summary))
    if summary.get("auth0") == "expired":
        print("warning: auth0 in this jar is already expired. Pushing it anyway.")
    users = load_local_users()
    targets = users
    if args.username:
        targets = [u for u in users if str(u.get("username")).lower() == args.username.lower()]
        if not targets:
            print("user not found", args.username)
            return 1
    for user in targets:
        name = str(user["username"])
        import_dat_store(name, "one", store, lst=lst, sst=sst, url=url_one)
        import_dat_store(name, "power", store, lst=lst, sst=sst, url="https://power.dat.com")
        print(f"pushed {len(store)} cookies -> {name} (one+power)")
    print("Done. Clients get new session on next Soft login / reconnect.")
    return 0


def cmd_import_store(args: argparse.Namespace) -> int:
    path = Path(args.cookies_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    # Accept either raw list of cookies, or {"store":[...], "lst":"{}", "sst":"", "url":"..."}
    if isinstance(data, list):
        store, lst, sst, url = data, "{}", "", args.url
    elif isinstance(data, dict):
        store = data.get("store") or data.get("cookies") or []
        lst = data.get("lst", "{}")
        sst = data.get("sst", "")
        url = args.url or data.get("url")
    else:
        print("cookies JSON must be a list or an object with store/cookies")
        return 1
    user = import_dat_store(args.username, args.stream, store, lst=str(lst), sst=str(sst), url=url)
    n = len((user.get("streams") or {}).get(args.stream, {}).get("store") or [])
    print(f"Imported {n} cookies into Soft user '{args.username}' stream '{args.stream}'")
    print("Every PC logging into that Soft user will receive the same DAT session + shared proxy IP.")
    return 0


def cmd_migrate(_: argparse.Namespace) -> int:
    stats = migrate_secrets()
    print("migration complete")
    print("dashboard_configured:", stats["dashboard_configured"])
    print("dashboard_password_hashed:", stats["dashboard_password_hashed"])
    print("dashboard_default_removed:", stats["dashboard_default_removed"])
    print("client_passwords_hashed:", stats["client_passwords_hashed"])
    print("session_key:", "present" if stats["session_key"] else "missing")
    pending = roster_only_usernames()
    if pending:
        print("roster usernames not on the server:", ", ".join(pending))
        print("Review them, then: python scripts/soft_admin.py import-roster --yes")
    return 0


def cmd_import_roster(args: argparse.Namespace) -> int:
    result = import_roster(apply=bool(args.yes))
    if not args.yes:
        print("not imported (pass --yes to hash these into the server store):")
        for name in result["pending"]:
            print(" -", name)
        if not result["pending"]:
            print("(none)")
        return 0
    print("imported:", ", ".join(result["imported"]) or "(none)")
    return 0


def cmd_roster_strip(_: argparse.Namespace) -> int:
    count = strip_roster_passwords()
    print(f"cleared passwords on {count} desktop roster row(s). Server logins were not changed.")
    return 0


def cmd_dashboard_set(args: argparse.Namespace) -> int:
    password = None
    if not args.generate_password:
        password = _secret_from_env_or_prompt("LANEORA_DASHBOARD_PASSWORD", "New dashboard password: ")
    generated = replace_dashboard_credentials(
        args.username or None,
        password,
        generate_username=bool(args.generate_username),
        generate_password=bool(args.generate_password),
    )
    print("dashboard sign-in replaced; existing admin sessions revoked")
    print("username:", generated.get("username") or generated.get("username_set"))
    if generated.get("password"):
        print("password:", generated["password"])
        print("Store this password now. It is not saved in plaintext and will not be shown again.")
    return 0


def cmd_sessions_revoke(_: argparse.Namespace) -> int:
    generation = revoke_all_sessions()
    print("admin sessions revoked")
    print("session_generation:", generation)
    return 0


def cmd_totp_enroll(args: argparse.Namespace) -> int:
    started = begin_totp()
    print("secret:", started["secret"])
    print("otpauth:", started["otpauth"])
    code = args.code or _secret_from_env_or_prompt("LANEORA_TOTP_CODE", "Current authenticator code: ")
    codes, _token = confirm_totp(code)
    print("two-factor authentication enabled; other admin sessions revoked")
    print("recovery codes (shown once):")
    for item in codes:
        print(item)
    return 0


def cmd_totp_disable(args: argparse.Namespace) -> int:
    password = _secret_from_env_or_prompt("LANEORA_DASHBOARD_PASSWORD", "Dashboard password: ")
    code = "" if args.lost_device else (
        args.code or _secret_from_env_or_prompt("LANEORA_TOTP_CODE", "Authenticator or recovery code: ")
    )
    disable_totp(password, code, lost_device=bool(args.lost_device))
    print("two-factor authentication disabled; admin sessions revoked")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Laneora Soft admin (shared IP + multi-PC)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="Show Soft config + accounts")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("multi-screen", help="Allow same Soft user on many PCs")
    p.add_argument("mode", choices=["on", "off"])
    p.set_defaults(func=cmd_multi)

    p = sub.add_parser("set-proxy", help="Shared HTTP proxy (same egress IP for all PCs)")
    p.add_argument("host", help="Proxy hostname/IP (use 'none' to clear)")
    p.add_argument("port", help="Proxy port")
    p.add_argument("username", nargs="?", default="", help="Proxy username")
    p.add_argument("password", nargs="?", default="", help="Proxy password")
    p.set_defaults(func=cmd_proxy)

    p = sub.add_parser("check-ip", help="Show egress IP DAT owners would see (via shared proxy)")
    p.set_defaults(func=cmd_check_ip)

    p = sub.add_parser("add-user", help="Create/update a Soft account")
    p.add_argument("username")
    p.add_argument("password")
    p.add_argument("--streams", default="one,power", help="Comma stream names (default one,power)")
    p.set_defaults(func=cmd_add_user)

    p = sub.add_parser("import-store", help="Import DAT cookie jar into a Soft user's stream")
    p.add_argument("username", help="Soft username")
    p.add_argument("stream", help="Stream name, usually one or power")
    p.add_argument("cookies_json", help="Path to cookie JSON export")
    p.add_argument("--url", default=None, help="Override stream URL")
    p.set_defaults(func=cmd_import_store)

    p = sub.add_parser(
        "capture-if-expired",
        help="Exit 2 when auth0 is missing or expired. Does not open Chrome.",
    )
    p.set_defaults(func=cmd_capture_if_expired)

    p = sub.add_parser(
        "push-capture",
        help="Push data/dat_cookies_captured.json to all Soft users (or one)",
    )
    p.add_argument("--file", default="", help="Cookie JSON path (default data/dat_cookies_captured.json)")
    p.add_argument("--username", default="", help="Only this Soft user (default: all)")
    p.set_defaults(func=cmd_push_capture)

    p = sub.add_parser("migrate", help="Hash plaintext dashboard and client passwords")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("import-roster", help="List or import desktop roster accounts missing on the server")
    p.add_argument("--yes", action="store_true", help="Hash the listed accounts into the server store")
    p.set_defaults(func=cmd_import_roster)

    p = sub.add_parser("roster-strip", help="Remove passwords from the desktop roster file")
    p.set_defaults(func=cmd_roster_strip)

    p = sub.add_parser("dashboard-set", help="Set the dashboard username and password")
    p.add_argument("--username", default="", help="Dashboard username. Omit to keep the current one.")
    p.add_argument("--generate-username", action="store_true", help="Generate a 32-character username and print it once")
    p.add_argument("--generate-password", action="store_true", help="Generate a 40-character password and print it once")
    p.set_defaults(func=cmd_dashboard_set)

    p = sub.add_parser("sessions-revoke", help="Sign out every dashboard browser")
    p.set_defaults(func=cmd_sessions_revoke)

    p = sub.add_parser("totp-enroll", help="Enroll an optional authenticator and print recovery codes once")
    p.add_argument("--code", default="", help="Prefer LANEORA_TOTP_CODE. A code confirms enrollment.")
    p.set_defaults(func=cmd_totp_enroll)

    p = sub.add_parser("totp-disable", help="Turn off dashboard two-factor authentication")
    p.add_argument("--code", default="")
    p.add_argument("--lost-device", action="store_true", help="Clear the factor with the dashboard password only")
    p.set_defaults(func=cmd_totp_disable)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
