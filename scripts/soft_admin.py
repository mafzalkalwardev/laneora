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
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import normalize_services  # noqa: E402
from server.soft_admin_lib import (  # noqa: E402
    check_egress_ip,
    import_dat_store,
    load_config,
    load_local_users,
    set_account_services,
    set_multi_screen,
    set_shared_proxy,
    upsert_account,
)


def cmd_status(_: argparse.Namespace) -> int:
    cfg = load_config()
    users = load_local_users()
    proxy = cfg.get("shared_proxy") or {}
    print("allow_multi_screen:", cfg.get("allow_multi_screen", True))
    print(
        "shared_proxy:",
        f"{proxy.get('px')}:{proxy.get('p')}",
        f"user={proxy.get('pu') or '(none)'}",
    )
    print(f"accounts ({len(users)}):")
    for user in users:
        streams = user.get("streams") or {}
        store_counts = {k: len((v or {}).get("store") or []) for k, v in streams.items()}
        print(
            f"  - {user.get('username')}  active={user.get('active', True)}  "
            f"plan={user.get('plan_label') or 'no plan'}  "
            f"ends={user.get('subscription_end') or '—'}  "
            f"subs={user.get('active_subs')}  "
            f"services={','.join(normalize_services(user.get('services') if 'services' in user else None))}  "
            f"px={user.get('px')}  cookies={store_counts}"
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
    services = None
    if str(args.services or "").strip():
        services = [s.strip() for s in str(args.services).split(",") if s.strip()]
    user = upsert_account(args.username, args.password, streams=streams, services=services)
    assigned = normalize_services(user.get("services") if "services" in user else None)
    print(
        "saved",
        user.get("username"),
        "subs=",
        user.get("active_subs"),
        "services=",
        ",".join(assigned),
        "px=",
        user.get("px"),
    )
    return 0


def cmd_set_services(args: argparse.Namespace) -> int:
    services = [s.strip() for s in str(args.services).split(",") if s.strip()]
    try:
        user = set_account_services(args.username, services)
    except ValueError as exc:
        print(exc)
        return 1
    print(user.get("username"), "services=", ",".join(user.get("services") or []))
    print("The dispatcher sees this on the next Laneora login.")
    return 0


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
    p.add_argument(
        "--services",
        default="",
        help="Comma service ids to assign (dat, dat_dual, dat_3, dat_6). Omit to leave the login on its current modules.",
    )
    p.set_defaults(func=cmd_add_user)

    p = sub.add_parser("set-services", help="Assign which modules a login can open")
    p.add_argument("username")
    p.add_argument("services", help="Comma service ids, for example dat,dat_dual or dat_3 or dat_6")
    p.set_defaults(func=cmd_set_services)

    p = sub.add_parser("import-store", help="Import DAT cookie jar into a Soft user's stream")
    p.add_argument("username", help="Soft username")
    p.add_argument("stream", help="Stream name, usually one or power")
    p.add_argument("cookies_json", help="Path to cookie JSON export")
    p.add_argument("--url", default=None, help="Override stream URL")
    p.set_defaults(func=cmd_import_store)

    p = sub.add_parser(
        "push-capture",
        help="Push data/dat_cookies_captured.json to all Soft users (or one)",
    )
    p.add_argument("--file", default="", help="Cookie JSON path (default data/dat_cookies_captured.json)")
    p.add_argument("--username", default="", help="Only this Soft user (default: all)")
    p.set_defaults(func=cmd_push_capture)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
