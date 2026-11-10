"""New DAT accounts copy the freshest auth0 jar, not a stale capture file."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

_ISOLATION = tempfile.mkdtemp(prefix="laneora-dat-session-")
os.environ["LANEORA_DATA_DIR"] = _ISOLATION

from server import security  # noqa: E402
from server.soft_admin_lib import (  # noqa: E402
    choose_dat_streams,
    create_account,
    dat_session_summary,
    format_dat_session,
    public_account,
)

NOW = 1_700_000_000
STALE = NOW - 86_400
FRESH = NOW + 86_400
FRESHER = NOW + 172_800


def _cookie(name: str, value: str, expires: float | None) -> dict:
    item = {"name": name, "value": value, "domain": ".dat.com", "path": "/"}
    if expires is not None:
        item["expirationDate"] = expires
    return item


def _jar(marker: str, auth_expires: float | None, cf_expires: float | None = None) -> list[dict]:
    cookies = [_cookie("auth0", marker, auth_expires)]
    if cf_expires is not None:
        cookies.append(_cookie("__cf_bm", "cf-" + marker, cf_expires))
    return cookies


def _user(name: str, marker: str, auth_expires: float | None, cf_expires: float | None = None) -> dict:
    return {
        "username": name,
        "streams": {
            "one": {
                "url": "https://one.dat.com/search-loads",
                "store": _jar(marker, auth_expires, cf_expires),
                "lst": "{}",
                "sst": "",
            }
        },
    }


def _auth_value(streams: dict) -> str:
    for cookie in streams["one"]["store"]:
        if cookie["name"] == "auth0":
            return str(cookie["value"])
    return ""


class DatSessionSelectTests(unittest.TestCase):
    def test_stale_capture_loses_to_a_later_user_jar(self) -> None:
        capture = {
            "url": "https://one.dat.com",
            "store": _jar("stale-capture", STALE),
            "lst": "{}",
            "sst": "",
        }
        users = [_user("dispatcher2", "live-user", FRESH, cf_expires=STALE)]
        chosen = choose_dat_streams(users, capture, now=NOW)
        self.assertEqual(_auth_value(chosen), "live-user")
        self.assertEqual(chosen["power"]["url"], "https://power.dat.com")
        self.assertEqual(_auth_value({"one": chosen["power"]}), "live-user")

    def test_fresh_capture_beats_an_older_user_jar(self) -> None:
        capture = {"store": _jar("fresh-capture", FRESHER), "lst": "{}", "sst": ""}
        users = [_user("dispatcher2", "older-user", FRESH)]
        chosen = choose_dat_streams(users, capture, now=NOW)
        self.assertEqual(_auth_value(chosen), "fresh-capture")

    def test_expired_cf_bm_does_not_reject_a_live_auth0(self) -> None:
        summary = dat_session_summary(_jar("live-auth", FRESH, cf_expires=STALE), now=NOW)
        self.assertEqual(summary["auth0"], "valid")
        self.assertEqual(summary["cf_bm"], "expired")
        self.assertNotIn("live-auth", json.dumps(summary))
        self.assertNotIn("cf-live-auth", json.dumps(summary))
        self.assertNotIn("value", summary)

    def test_both_expired_picks_the_later_auth0_not_the_capture_file(self) -> None:
        capture = {"store": _jar("older-expired", STALE - 10_000)}
        users = [_user("dispatcher2", "newer-expired", STALE)]
        chosen = choose_dat_streams(users, capture, now=NOW)
        self.assertEqual(_auth_value(chosen), "newer-expired")
        summary = dat_session_summary(chosen["one"]["store"], now=NOW)
        self.assertEqual(summary["auth0"], "expired")

    def test_equal_expiry_keeps_the_canonical_capture(self) -> None:
        capture = {"store": _jar("canonical", FRESH)}
        users = [_user("dispatcher2", "same-age", FRESH)]
        chosen = choose_dat_streams(users, capture, now=NOW)
        self.assertEqual(_auth_value(chosen), "canonical")

    def test_capture_without_auth0_loses_to_a_user_who_has_one(self) -> None:
        capture = {"store": [_cookie("did", "capture-did", FRESHER)]}
        users = [_user("dispatcher2", "user-auth", FRESH)]
        chosen = choose_dat_streams(users, capture, now=NOW)
        self.assertEqual(_auth_value(chosen), "user-auth")

    def test_empty_sources_stay_empty(self) -> None:
        chosen = choose_dat_streams([], {"store": []}, now=NOW)
        self.assertEqual(chosen["one"]["store"], [])
        summary = dat_session_summary(chosen["one"]["store"], now=NOW)
        self.assertEqual(summary["auth0"], "missing")
        self.assertEqual(summary["cookies"], 0)

    def test_summary_text_has_no_cookie_secret(self) -> None:
        summary = dat_session_summary(_jar("super-secret-token", FRESH), now=NOW)
        text = format_dat_session(summary)
        self.assertIn("auth0=valid", text)
        self.assertNotIn("super-secret-token", text)
        account = public_account(
            {
                "username": "shayan",
                "password_hash": "pbkdf2_sha256$1$aa$bb",
                "active": True,
                "streams": {"one": {"store": _jar("super-secret-token", time.time() + 86_400)}},
            }
        )
        encoded = json.dumps(account)
        self.assertNotIn("super-secret-token", encoded)
        self.assertNotIn("password", account)
        self.assertEqual(account["dat_session"]["auth0"], "valid")

    def test_create_account_stores_the_fresher_user_jar(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        os.environ["LANEORA_DATA_DIR"] = temporary.name
        security.PBKDF2_ITERATIONS = 1_200
        root = Path(temporary.name)
        root.mkdir(parents=True, exist_ok=True)
        real_now = time.time()
        (root / "dat_cookies_captured.json").write_text(
            json.dumps({"url": "https://one.dat.com", "store": _jar("stale-capture", real_now - 86_400)}),
            encoding="utf-8",
        )
        (root / "local_users.json").write_text(
            json.dumps({"users": [_user("dispatcher2", "live-user", real_now + 86_400)]}),
            encoding="utf-8",
        )
        created = create_account("shayan", "shayan-pass-1", "day_1")
        self.assertEqual(created["dat_session"]["auth0"], "valid")
        self.assertNotIn("live-user", json.dumps(created))
        self.assertNotIn("stale-capture", json.dumps(created))
        saved = json.loads((root / "local_users.json").read_text(encoding="utf-8"))
        stored = next(user for user in saved["users"] if user["username"] == "shayan")
        values = [cookie["value"] for cookie in stored["streams"]["one"]["store"]]
        self.assertIn("live-user", values)
        self.assertNotIn("stale-capture", values)
        self.assertNotIn("shayan-pass-1", json.dumps(saved))


if __name__ == "__main__":
    unittest.main()
