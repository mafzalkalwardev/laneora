"""Service assignment: original DAT Search stays the default; dual search is opt-in."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from app import PASSPHRASE
from app.auth import AuthSession
from app.crypto_util import decrypt
from app.services import (
    DAT,
    DAT_DUAL,
    DUAL_SEARCH_TABS,
    normalize_services,
    require_services,
    search_url,
)
from server.soft_shim import Handler, _build_auth_payload

ROOT = Path(__file__).resolve().parents[1]


class ServiceRulesTest(unittest.TestCase):
    def test_missing_list_is_original_module(self) -> None:
        self.assertEqual(normalize_services(None), [DAT])
        self.assertEqual(normalize_services(""), [DAT])
        self.assertEqual(normalize_services([]), [DAT])
        self.assertEqual(normalize_services(["not-a-module"]), [DAT])

    def test_assignment_keeps_catalog_order_and_rejects_unknown(self) -> None:
        self.assertEqual(require_services(["dat_dual", "dat"]), [DAT, DAT_DUAL])
        self.assertEqual(require_services("dat_dual"), [DAT_DUAL])
        self.assertEqual(normalize_services("dat,bogus,dat_dual"), [DAT, DAT_DUAL])
        with self.assertRaises(ValueError):
            require_services([])
        with self.assertRaises(ValueError):
            require_services(["nope"])

    def test_dual_module_is_two_distinct_search_tabs(self) -> None:
        self.assertEqual(len(DUAL_SEARCH_TABS), 2)
        self.assertEqual(len(set(DUAL_SEARCH_TABS)), 2)

    def test_search_url_matches_original_dat_rules(self) -> None:
        self.assertEqual(search_url({"url": "https://one.dat.com"}, "one"), "https://one.dat.com/search-loads")
        self.assertEqual(
            search_url({"url": "https://one.dat.com/dashboard"}, "one"),
            "https://one.dat.com/search-loads",
        )
        self.assertEqual(search_url({"url": "https://power.dat.com/anything"}, "power"), "https://power.dat.com")
        self.assertEqual(search_url({"url": "https://example.test/board"}, "one"), "https://example.test/board")
        self.assertEqual(search_url({}, "one"), "https://one.dat.com/search-loads")

    def test_auth_session_defaults_when_server_omits_services(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, {"status": "okie", "one": "blob"})
        self.assertEqual(session.services, [DAT])
        session.resp["services"] = "dat,dat_dual"
        self.assertEqual(session.services, [DAT, DAT_DUAL])
        session.resp["services"] = ["dat_dual"]
        self.assertEqual(session.services, [DAT_DUAL])

    def test_existing_accounts_stay_on_dat_search(self) -> None:
        raw = json.loads((ROOT / "data" / "local_users.json").read_text(encoding="utf-8"))
        before = json.dumps(raw)
        names = []
        for user in raw["users"]:
            self.assertNotIn("services", user)
            names.append(user["username"])
            payload = _build_auth_payload(user)
            self.assertEqual(payload["services"], DAT)
            self.assertIn("one", payload)
            plain = json.loads(decrypt(PASSPHRASE, payload["one"]))
            self.assertIn("dat.com", plain["url"])
        self.assertIn("mafzalk", names)
        dispatcher = next(user for user in raw["users"] if user["username"] == "dispatcher2")
        both = _build_auth_payload(dispatcher)
        self.assertIn("power", both)
        self.assertEqual(json.dumps(raw), before)

    def test_assigned_dual_search_still_includes_dat_one_session(self) -> None:
        user = {
            "username": "dual",
            "password": "secret",
            "active_subs": ["power"],
            "services": ["dat_dual", "dat"],
            "px": "none",
            "p": "0",
            "pu": "",
            "pd": "",
            "streams": {"power": {"url": "https://power.dat.com", "store": [], "lst": "{}", "sst": ""}},
        }
        payload = _build_auth_payload(user)
        self.assertEqual(payload["services"], "dat,dat_dual")
        self.assertEqual(payload["active_subs"], "power")
        plain = json.loads(decrypt(PASSPHRASE, payload["one"]))
        self.assertEqual(plain["url"], "https://one.dat.com")
        self.assertIn("power", payload)

    def test_original_screen_still_hides_its_single_tab(self) -> None:
        text = (ROOT / "app" / "window.py").read_text(encoding="utf-8")
        self.assertIn("self.tabs.tabBar().hide()", text)
        self.assertIn("QWebEngineProfile(view)", text)
        self.assertIn("DUAL_SEARCH_TABS", text)
        html = (ROOT / "server" / "admin_dashboard.html").read_text(encoding="utf-8")
        self.assertIn('data-act="services"', html)
        self.assertIn('id="newServices"', html)


class AdminAssignmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.users_path = root / "local_users.json"
        self.users_path.write_text('{"users": []}\n', encoding="utf-8")
        self.cfg_path = root / "soft_config.json"
        self.roster_path = root / "users.json"
        self.roster_path.write_text('{"users": []}\n', encoding="utf-8")
        self.patches = [
            patch("server.soft_admin_lib.LOCAL_USERS_FILE", self.users_path),
            patch("server.soft_admin_lib.SOFT_CONFIG_FILE", self.cfg_path),
            patch("server.soft_admin_lib._CAPTURED_COOKIES", root / "no-capture.json"),
            patch("server.soft_shim.USERS_FILE", self.roster_path),
            patch("app.roster.USERS_FILE", self.roster_path),
            patch("app.roster.DATA_DIR", root),
        ]
        for item in self.patches:
            item.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.http = requests.Session()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def _login(self) -> None:
        response = self.http.post(
            self.base + "/admin/api/login",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])

    def test_admin_assigns_dual_search_and_login_receives_it(self) -> None:
        self._login()
        created = self.http.post(
            self.base + "/admin/api/users",
            json={"username": "plainuser", "password": "secret1", "plan": "day_1"},
            timeout=10,
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["user"]["services"], [DAT])

        listed = self.http.get(self.base + "/admin/api/users", timeout=10)
        body = listed.json()
        self.assertEqual(body["users"][0]["services"], [DAT])
        self.assertIn(DAT_DUAL, [item["id"] for item in body["services"]])

        both = self.http.post(
            self.base + "/admin/api/users/update",
            json={"username": "plainuser", "services": [DAT_DUAL, DAT]},
            timeout=10,
        )
        self.assertEqual(both.status_code, 200, both.text)
        self.assertEqual(both.json()["user"]["services"], [DAT, DAT_DUAL])

        rejected = self.http.post(
            self.base + "/admin/api/users/update",
            json={"username": "plainuser", "services": []},
            timeout=10,
        )
        self.assertEqual(rejected.status_code, 400)
        unknown = self.http.post(
            self.base + "/admin/api/users/update",
            json={"username": "plainuser", "services": ["nope"]},
            timeout=10,
        )
        self.assertEqual(unknown.status_code, 400)
        # A rejected save does not clear the previous assignment.
        self.assertEqual(
            self.http.get(self.base + "/admin/api/users", timeout=10).json()["users"][0]["services"],
            [DAT, DAT_DUAL],
        )

        auth = requests.get(
            self.base + "/authenticate",
            params={"username": "plainuser", "key": "secret1", "value": "7", "is_alive": "3"},
            timeout=10,
        )
        payload = auth.json()
        self.assertEqual(payload["status"], "okie")
        self.assertEqual(payload["services"], "dat,dat_dual")
        self.assertIn("one", payload)
        plain = json.loads(decrypt(PASSPHRASE, payload["one"]))
        self.assertIn("one.dat.com", plain["url"])

        only_dual = self.http.post(
            self.base + "/admin/api/users",
            json={
                "username": "dualonly",
                "password": "secret1",
                "plan": "trial_1h",
                "services": ["dat_dual"],
            },
            timeout=10,
        )
        self.assertEqual(only_dual.status_code, 200, only_dual.text)
        self.assertEqual(only_dual.json()["user"]["services"], [DAT_DUAL])
        dual_auth = requests.get(
            self.base + "/authenticate",
            params={"username": "dualonly", "key": "secret1", "value": "8", "is_alive": "4"},
            timeout=10,
        )
        self.assertEqual(dual_auth.json()["services"], "dat_dual")


if __name__ == "__main__":
    unittest.main()
