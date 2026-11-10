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
    DAT_3,
    DAT_4,
    DAT_DUAL,
    DUAL_SEARCH_TABS,
    MULTI_SEARCH_TABS,
    normalize_services,
    opens_dat_search,
    require_services,
    search_open_delay_ms,
    search_tab_titles,
    search_url,
    service_catalog,
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
        self.assertEqual(
            require_services(["dat_4", "dat", "dat_3", "dat_dual"]),
            [DAT, DAT_DUAL, DAT_3, DAT_4],
        )
        self.assertEqual(require_services("dat_3"), [DAT_3])
        self.assertEqual(require_services("dat_4"), [DAT_4])
        self.assertEqual(normalize_services("dat_4,bogus,dat_3"), [DAT_3, DAT_4])
        self.assertEqual(normalize_services(["dat_6"]), [DAT])
        self.assertEqual(normalize_services("dat_6,dat_3"), [DAT_3])
        with self.assertRaises(ValueError):
            require_services([])
        with self.assertRaises(ValueError):
            require_services(["nope"])
        with self.assertRaises(ValueError):
            require_services(["dat_6"])

    def test_catalog_lists_each_module_once(self) -> None:
        self.assertEqual(
            [item["id"] for item in service_catalog()],
            [DAT, DAT_DUAL, DAT_3, DAT_4],
        )

    def test_dual_module_is_two_distinct_search_tabs(self) -> None:
        self.assertEqual(len(DUAL_SEARCH_TABS), 2)
        self.assertEqual(len(set(DUAL_SEARCH_TABS)), 2)
        self.assertEqual(DUAL_SEARCH_TABS, ("Search 1", "Search 2"))

    def test_three_and_four_open_that_many_distinct_tabs(self) -> None:
        self.assertEqual(MULTI_SEARCH_TABS[DAT_DUAL], 2)
        self.assertEqual(MULTI_SEARCH_TABS[DAT_3], 3)
        self.assertEqual(search_tab_titles(3), ("Search 1", "Search 2", "Search 3"))
        self.assertEqual(MULTI_SEARCH_TABS[DAT_4], 4)
        titles = search_tab_titles(4)
        self.assertEqual(titles, ("Search 1", "Search 2", "Search 3", "Search 4"))
        self.assertEqual(len(set(titles)), 4)
        self.assertNotIn("dat_6", MULTI_SEARCH_TABS)
        self.assertTrue(opens_dat_search(DAT))
        self.assertTrue(opens_dat_search(DAT_DUAL))
        self.assertTrue(opens_dat_search(DAT_3))
        self.assertTrue(opens_dat_search(DAT_4))
        # Dual keeps the original simultaneous 400ms open. 3 and 4 stagger.
        self.assertEqual(search_open_delay_ms(0, 2), 400)
        self.assertEqual(search_open_delay_ms(1, 2), 400)
        self.assertEqual(search_open_delay_ms(0, 4), 400)
        self.assertEqual(search_open_delay_ms(3, 4), 400 + 3 * 350)
        self.assertGreater(search_open_delay_ms(3, 4), search_open_delay_ms(1, 3))

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
        session.resp["services"] = "dat_4,dat_3"
        self.assertEqual(session.services, [DAT_3, DAT_4])
        session.resp["services"] = ["dat_3"]
        self.assertEqual(session.services, [DAT_3])

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

    def test_three_and_four_still_include_the_shared_dat_session(self) -> None:
        for service_id in (DAT_3, DAT_4):
            user = {
                "username": service_id,
                "password": "secret",
                "active_subs": ["power"],
                "services": [service_id],
                "px": "none",
                "p": "0",
                "pu": "",
                "pd": "",
                "streams": {"power": {"url": "https://power.dat.com", "store": [], "lst": "{}", "sst": ""}},
            }
            payload = _build_auth_payload(user)
            self.assertEqual(payload["services"], service_id)
            self.assertEqual(payload["active_subs"], "power")
            plain = json.loads(decrypt(PASSPHRASE, payload["one"]))
            self.assertEqual(plain["url"], "https://one.dat.com")
            self.assertIn("power", payload)

    def test_original_screen_still_hides_its_single_tab(self) -> None:
        text = (ROOT / "app" / "window.py").read_text(encoding="utf-8")
        self.assertIn("self.tabs.tabBar().hide()", text)
        self.assertIn("QWebEngineProfile(view)", text)
        self.assertIn("def browse_dual", text)
        self.assertIn("def browse_multi", text)
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

    def test_admin_assigns_three_and_four_without_changing_other_users(self) -> None:
        self._login()
        for username, services in (
            ("classic", None),
            ("only3", [DAT_3]),
            ("only4", [DAT_4]),
        ):
            body: dict = {"username": username, "password": "secret1", "plan": "day_1"}
            if services is not None:
                body["services"] = services
            created = self.http.post(self.base + "/admin/api/users", json=body, timeout=10)
            self.assertEqual(created.status_code, 200, created.text)

        listed = self.http.get(self.base + "/admin/api/users", timeout=10).json()
        by_name = {user["username"]: user["services"] for user in listed["users"]}
        catalog = [item["id"] for item in listed["services"]]
        self.assertEqual(catalog, [DAT, DAT_DUAL, DAT_3, DAT_4])
        self.assertEqual(by_name["classic"], [DAT])
        self.assertEqual(by_name["only3"], [DAT_3])
        self.assertEqual(by_name["only4"], [DAT_4])
        self.assertNotIn("dat_6", catalog)

        both = self.http.post(
            self.base + "/admin/api/users/update",
            json={"username": "only3", "services": [DAT_4, DAT, DAT_3]},
            timeout=10,
        )
        self.assertEqual(both.status_code, 200, both.text)
        self.assertEqual(both.json()["user"]["services"], [DAT, DAT_3, DAT_4])

        rejected = self.http.post(
            self.base + "/admin/api/users/update",
            json={"username": "only4", "services": []},
            timeout=10,
        )
        self.assertEqual(rejected.status_code, 400)
        unknown = self.http.post(
            self.base + "/admin/api/users/update",
            json={"username": "only4", "services": ["dat_6"]},
            timeout=10,
        )
        self.assertEqual(unknown.status_code, 400)

        after = {
            user["username"]: user["services"]
            for user in self.http.get(self.base + "/admin/api/users", timeout=10).json()["users"]
        }
        self.assertEqual(after["classic"], [DAT])
        self.assertEqual(after["only3"], [DAT, DAT_3, DAT_4])
        self.assertEqual(after["only4"], [DAT_4])

        classic_auth = requests.get(
            self.base + "/authenticate",
            params={"username": "classic", "key": "secret1", "value": "1", "is_alive": "1"},
            timeout=10,
        )
        three_auth = requests.get(
            self.base + "/authenticate",
            params={"username": "only3", "key": "secret1", "value": "2", "is_alive": "2"},
            timeout=10,
        )
        four_auth = requests.get(
            self.base + "/authenticate",
            params={"username": "only4", "key": "secret1", "value": "3", "is_alive": "3"},
            timeout=10,
        )
        self.assertEqual(classic_auth.json()["services"], DAT)
        self.assertEqual(three_auth.json()["services"], "dat,dat_3,dat_4")
        self.assertEqual(four_auth.json()["services"], DAT_4)
        for response in (classic_auth, three_auth, four_auth):
            plain = json.loads(decrypt(PASSPHRASE, response.json()["one"]))
            self.assertIn("one.dat.com", plain["url"])

    def test_cli_set_services_assigns_each_module(self) -> None:
        import importlib.util

        self._login()
        for username in ("staydat", "threeuser", "fouruser", "dualuser"):
            created = self.http.post(
                self.base + "/admin/api/users",
                json={"username": username, "password": "secret1", "plan": "week_1"},
                timeout=10,
            )
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["user"]["services"], [DAT])

        spec = importlib.util.spec_from_file_location("soft_admin_cli", ROOT / "scripts" / "soft_admin.py")
        assert spec is not None and spec.loader is not None
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)

        def run_set(*args: str) -> int:
            with patch("sys.argv", ["soft_admin.py", "set-services", *args]):
                return cli.main()

        self.assertEqual(run_set("threeuser", "dat_3"), 0)
        self.assertEqual(run_set("fouruser", "dat_4"), 0)
        self.assertEqual(run_set("dualuser", "dat_dual"), 0)
        self.assertEqual(run_set("threeuser", "nope"), 1)
        self.assertEqual(run_set("fouruser", "dat_6"), 1)
        self.assertEqual(run_set("missinguser", "dat_3"), 1)

        listed = {
            user["username"]: user["services"]
            for user in self.http.get(self.base + "/admin/api/users", timeout=10).json()["users"]
        }
        self.assertEqual(listed["staydat"], [DAT])
        self.assertEqual(listed["threeuser"], [DAT_3])
        self.assertEqual(listed["fouruser"], [DAT_4])
        self.assertEqual(listed["dualuser"], [DAT_DUAL])

        self.assertEqual(run_set("threeuser", "dat,dat_4"), 0)
        listed = {
            user["username"]: user["services"]
            for user in self.http.get(self.base + "/admin/api/users", timeout=10).json()["users"]
        }
        self.assertEqual(listed["threeuser"], [DAT, DAT_4])
        self.assertEqual(listed["fouruser"], [DAT_4])
        self.assertEqual(listed["dualuser"], [DAT_DUAL])
        self.assertEqual(listed["staydat"], [DAT])

        auth = requests.get(
            self.base + "/authenticate",
            params={"username": "fouruser", "key": "secret1", "value": "9", "is_alive": "9"},
            timeout=10,
        )
        self.assertEqual(auth.json()["services"], "dat_4")
        plain = json.loads(decrypt(PASSPHRASE, auth.json()["one"]))
        self.assertIn("one.dat.com", plain["url"])


if __name__ == "__main__":
    unittest.main()
