"""Probe soft.awwthat.com /authenticate response shapes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.roster import load_roster  # noqa: E402


def main() -> None:
    users = load_roster()
    u = next((x for x in users if x["username"] == "mafzalk"), None)
    if not u:
        print("mafzalk not in roster")
        return
    user, password = u["username"], u["password"]
    print("trying", user, "pw_len", len(password))

    attempts = [
        ("https://soft.awwthat.com", {"Accept": "application/json"}),
        ("https://soft.awwthat.com", {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}),
        (
            "https://soft.awwthat.com",
            {
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            },
        ),
        ("http://soft.awwthat.com", {"Accept": "application/json"}),
    ]
    for base, headers in attempts:
        params = {
            "username": user.lower(),
            "key": password.lower(),
            "value": "12345",
            "is_alive": "9",
        }
        r = requests.get(base + "/authenticate", params=params, headers=headers, timeout=30)
        print("---", base, r.status_code, r.headers.get("content-type"))
        print(repr(r.text[:400]))
        title = re.search(r"<title>(.*?)</title>", r.text, re.I | re.S)
        if title:
            print("title:", re.sub(r"<[^>]+>", "", title.group(1)).strip()[:200])
        # Laravel JSON error
        if r.headers.get("content-type", "").startswith("application/json"):
            print("json body:", r.text[:500])

    # raw literal password (no lower)
    r = requests.get(
        "https://soft.awwthat.com/authenticate",
        params={"username": user, "key": password, "value": 1, "is_alive": 1},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    print("--- no-lower", r.status_code, repr(r.text[:400]))


if __name__ == "__main__":
    main()
