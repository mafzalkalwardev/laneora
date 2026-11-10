"""Two DAT searches are an admin plan. Old accounts and old payloads stay one tab."""
from __future__ import annotations

import json
import unittest

from app.crypto_util import decrypt
from app.search_tabs import can_open_another_search, entitled_search_tabs
from app import PASSPHRASE
from server.soft_shim import _build_auth_payload
from server.soft_admin_lib import public_account
from server.subscriptions import account_searches, apply_plan, get_plan


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

    def test_x2_plan_assigns_two_searches_for_the_same_length(self) -> None:
        one = get_plan("week_1")
        two = get_plan("week_1_x2")
        self.assertEqual(one["delta"], two["delta"])
        user = {"username": "shayan", "searches": 1, "plan": "week_1"}
        apply_plan(user, "week_1_x2", extend=False)
        self.assertEqual(user["searches"], 2)
        self.assertIn("2 searches", user["plan_label"])

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
        stream = json.loads(decrypt(PASSPHRASE, payload["one"]))
        self.assertEqual(stream["store"][0]["name"], "auth0")
        plain = dict(user)
        plain.pop("searches")
        self.assertEqual(_build_auth_payload(plain)["max_searches"], 1)

    def test_client_opens_one_tab_until_the_plus(self) -> None:
        self.assertEqual(entitled_search_tabs({}), 1)
        self.assertEqual(entitled_search_tabs({"status": "okie"}), 1)
        self.assertEqual(entitled_search_tabs({"max_searches": "2"}), 2)
        self.assertEqual(entitled_search_tabs({"max_searches": 9}), 2)
        self.assertFalse(can_open_another_search(1, 1))
        self.assertTrue(can_open_another_search(1, 2))
        self.assertFalse(can_open_another_search(2, 2))
        self.assertFalse(can_open_another_search(0, 1))


if __name__ == "__main__":
    unittest.main()
