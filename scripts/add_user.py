"""Inject a test user into data/users.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import USERS_FILE  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Add or update a Laneora local test user")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument(
        "--streams",
        default="one,power",
        help="Comma-separated stream names (default: one,power)",
    )
    parser.add_argument("--url-one", default="https://one.dat.com")
    parser.add_argument("--url-power", default="https://power.dat.com")
    parser.add_argument("--px", default="none", help="Proxy host, or 'none' for direct")
    parser.add_argument("--p", default="0", help="Proxy port")
    parser.add_argument("--pu", default="", help="Proxy username")
    parser.add_argument("--pd", default="", help="Proxy password")
    args = parser.parse_args()

    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if USERS_FILE.exists():
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    else:
        data = {"users": []}

    stream_names = [s.strip() for s in args.streams.split(",") if s.strip()]
    streams = {}
    for name in stream_names:
        url = args.url_power if "power" in name.lower() else args.url_one
        if name.lower() == "one":
            url = args.url_one
        if name.lower() == "power":
            url = args.url_power
        streams[name] = {"url": url, "store": [], "lst": "{}", "sst": ""}

    username = args.username.strip().lower()
    password = args.password.strip().lower()
    users = data.setdefault("users", [])
    updated = False
    for user in users:
        if str(user.get("username", "")).lower() == username:
            user.update(
                {
                    "username": username,
                    "password": password,
                    "active": True,
                    "active_subs": stream_names,
                    "px": args.px,
                    "p": args.p,
                    "pu": args.pu,
                    "pd": args.pd,
                    "streams": streams,
                }
            )
            updated = True
            break
    if not updated:
        users.append(
            {
                "username": username,
                "password": password,
                "active": True,
                "active_subs": stream_names,
                "px": args.px,
                "p": args.p,
                "pu": args.pu,
                "pd": args.pd,
                "streams": streams,
            }
        )

    USERS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    action = "Updated" if updated else "Added"
    print(f"{action} user '{username}' in {USERS_FILE}")
    print(f"Login with: {username} / {password}")


if __name__ == "__main__":
    main()
