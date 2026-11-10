"""Two DAT searches are an admin plan. Old accounts and old payloads stay one tab."""
from __future__ import annotations

import json
import unittest

from app.crypto_util import decrypt
from app.search_tabs import can_open_another_search, entitled_search_tabs, switch_keeps_tabs
from app import PASSPHRASE
from server.soft_shim import _build_auth_payload
from server.soft_admin_lib import public_account
from server.subscriptions import account_searches, apply_plan, denial_payload, get_plan


class TwoSearchTests(unittest.TestCase):
    def test_missing_field_stays_one_search_and_is_not_written(self) -> None:
        user = {"username": "dispatcher2", "plan": "month_1"}
        self.assertEqual(account_searches(user), 1)
        self.assertNotIn("searches", user)
        shown = public_account(user)
        self.assertEqual(shown["searches"], 1)
        self.assertNotIn("searches", user)

    def test_original_plan_ids_remain_one_search(self) -> None:
        plan = get_plan("day_1")
        self.assertEqual(plan["searches"], 1)
        user = {"username": "dispatcher2"}
        apply_plan(user, "day_1", extend=False)
        self.assertEqual(user["plan"], "day_1")
        self.assertEqual(user["searches"], 1)
        self.assertEqual(account_searches(user), 1)

    def test_each_duration_has_four_search_tiers(self) -> None:
        for base, suffix, count in (
            ("week_1", "", 1),
            ("week_1_x2", "_x2", 2),
            ("week_1_x3", "_x3", 3),
            ("week_1_x6", "_x6", 6),
        ):
            plan = get_plan(base)
            self.assertEqual(plan["searches"], count)
            self.assertEqual(plan["delta"], get_plan("week_1")["delta"])
        user = {"username": "shayan", "searches": 1, "plan": "week_1"}
        apply_plan(user, "week_1_x6", extend=False)
        self.assertEqual(user["searches"], 6)
        apply_plan(user, "week_1", extend=True)
        self.assertEqual(user["searches"], 1)
        self.assertEqual(user["plan"], "week_1")

    def test_unknown_search_count_does_not_upgrade(self) -> None:
        for raw in (0, 4, 5, 9, "nope"):
            self.assertEqual(account_searches({"searches": raw}), 1)
            self.assertEqual(entitled_search_tabs({"max_searches": raw}), 1)

    def test_authenticate_payload_keeps_old_fields_and_adds_max_searches(self) -> None:
        user = {
            "username": "shayan",
            "password_hash": "pbkdf2_sha256$600000$aa$bb",
            "active": True,
            "active_subs": ["one"],
            "px": "none",
            "p": "0",
            "pu": "",
            "pd": "",
            "searches": 2,
            "streams": {
                "one": {
                    "url": "https://one.dat.com",
                    "store": [{"name": "auth0", "value": "secret-cookie"}],
                    "lst": "{}",
                    "sst": "",
                }
            },
        }
        payload = _build_auth_payload(user)
        self.assertEqual(payload["status"], "okie")
        self.assertEqual(payload["active_subs"], "one")
        self.assertEqual(payload["px"], "none")
        self.assertEqual(payload["max_searches"], 2)
        for count in (1, 2, 3, 6):
            tier = dict(user)
            tier["searches"] = count
            self.assertEqual(_build_auth_payload(tier)["max_searches"], count)
        stream = json.loads(decrypt(PASSPHRASE, payload["one"]))
        self.assertEqual(stream["store"][0]["name"], "auth0")
        plain = dict(user)
        plain.pop("searches")
        self.assertEqual(_build_auth_payload(plain)["max_searches"], 1)

    def test_plus_stops_at_each_cap_and_switch_keeps_tabs(self) -> None:
        self.assertEqual(entitled_search_tabs({}), 1)
        self.assertEqual(entitled_search_tabs({"status": "okie"}), 1)
        for cap in (1, 2, 3, 6):
            opened = 1
            while can_open_another_search(opened, cap):
                opened += 1
            self.assertEqual(opened, cap)
            self.assertFalse(can_open_another_search(opened, cap))
        self.assertFalse(can_open_another_search(1, 1))
        self.assertTrue(can_open_another_search(2, 3))
        self.assertFalse(can_open_another_search(3, 3))
        self.assertTrue(can_open_another_search(5, 6))
        self.assertFalse(can_open_another_search(6, 6))
        still_open, index = switch_keeps_tabs(6, 0, 4)
        self.assertEqual((still_open, index), (6, 4))
        self.assertEqual(switch_keeps_tabs(3, 1, 9), (3, 1))

    def test_expired_multi_search_plan_cannot_log_in(self) -> None:
        user = {"username": "shayan", "active": True, "searches": 6, "plan_label": "1 week, 6 searches"}
        apply_plan(user, "week_1_x6", extend=False)
        user["subscription_end"] = "2000-01-01T00:00:00Z"
        denied = denial_payload(user)
        self.assertIsNotNone(denied)
        self.assertEqual(denied["status"], "expired")


if __name__ == "__main__":
    unittest.main()
