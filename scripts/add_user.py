"""Inject a soft.awwthat.com credential into the local Laneora roster."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import users_file  # noqa: E402
from app.roster import load_roster, upsert_user  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add or update a soft.awwthat.com login in data/users.json"
    )
    parser.add_argument("username", help="Soft account username")
    parser.add_argument("password", help="Soft account password")
    parser.add_argument("--label", default="", help="Optional display label in the login dropdown")
    args = parser.parse_args()

    upsert_user(args.username, args.password, args.label or None)
    users = load_roster()
    print(f"Saved '{args.username}' to {users_file()}")
    print(f"Roster now has {len(users)} user(s). Login still authenticates against soft.awwthat.com.")


if __name__ == "__main__":
    main()
