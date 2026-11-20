"""Load search API: a Laneora login can search loads and cannot manage users."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from server.soft_admin_lib import create_account, update_account
from server.soft_shim import Handler


def _board_user(root: Path) -> None:
    user = create_account("dispatcher", "secret1", "day_1")
    users = json.loads((root / "local_users.json").read_text(encoding="utf-8"))
    for account in users["users"]:
        if account["username"] == user["username"]:
            account["streams"]["one"]["lst"] = json.dumps(
                {"@@auth0spajs@@::laneora": {"body": {"access_token": "eyJhbGci.payload.signature"}}}
            )
    (root / "local_users.json").write_text(json.dumps(users), encoding="utf-8")


class LoadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "local_users.json").write_text('{"users": []}\n', encoding="utf-8")
        (root / "users.json").write_text('{"users": []}\n', encoding="utf-8")
        self.root = root
        self.patches = [
            patch("server.soft_admin_lib.LOCAL_USERS_FILE", root / "local_users.json"),
            patch("server.soft_admin_lib.SOFT_CONFIG_FILE", root / "soft_config.json"),
            patch("server.soft_admin_lib._CAPTURED_COOKIES", root / "no-capture.json"),
            patch("server.soft_shim.USERS_FILE", root / "users.json"),
            patch("app.roster.USERS_FILE", root / "users.json"),
            patch("app.roster.DATA_DIR", root),
        ]
        for item in self.patches:
            item.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def _token(self) -> str:
        response = requests.post(
            self.base + "/api/v1/session",
            json={"username": "dispatcher", "password": "secret1"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["scope"], "loads")
        return body["token"]

    def test_index_is_load_search_and_user_admin_is_gone(self) -> None:
        index = requests.get(self.base + "/api/v1", timeout=10)
        self.assertEqual(index.status_code, 200, index.text)
        paths = [route["path"] for route in index.json()["routes"]]
        self.assertIn("/api/v1/loads/search", paths)
        self.assertNotIn("/api/v1/users", paths)
        self.assertEqual(index.json()["scope"], "loads")
        blocked = requests.post(self.base + "/api/v1/users", json={"username": "x"}, timeout=10)
        self.assertEqual(blocked.status_code, 404, blocked.text)
        self.assertIn("loads only", blocked.json()["error"])

    def test_dashboard_password_is_not_a_load_token(self) -> None:
        _board_user(self.root)
        response = requests.post(
            self.base + "/api/v1/session",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_disabled_account_cannot_search(self) -> None:
        _board_user(self.root)
        update_account("dispatcher", active=False)
        response = requests.post(
            self.base + "/api/v1/session",
            json={"username": "dispatcher", "password": "secret1"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertIn("disabled", response.json()["error"].lower())

    def test_search_returns_load_details_and_detail_lookup(self) -> None:
        _board_user(self.root)
        token = self._token()
        seen: dict = {}

        def transport(board_token: str, cookie: str, query: str, variables: dict) -> dict:
            seen["token"] = board_token
            seen["query"] = query
            seen["variables"] = variables
            if "LoadDetails" in query:
                return {
                    "data": {
                        "searchLoadDetailsWithRates": {
                            "searchLoadDetails": {
                                "__typename": "LoadDetailsResponse",
                                "searchLoadDetails": {
                                    "id": "row-1",
                                    "matchId": "lane+row-1",
                                    "dotIds": {"brokerMcNumber": "123456", "carrierMcNumber": "", "dotNumber": "999"},
                                    "peerRatingSummary": {"averageRating": 4.5, "numberOfRatings": 12},
                                },
                            }
                        }
                    }
                }
            return {
                "data": {
                    "createAndExecuteSearch": {
                        "__typename": "SearchCreateAndExecutionResponse",
                        "searchResponse": {"search": {"id": "search-9"}},
                        "matchResponse": {
                            "count": 1,
                            "matches": [
                                {
                                    "id": "row-1",
                                    "matchId": "lane+row-1",
                                    "postingId": "P1",
                                    "availability": {"earliest": "2026-11-20", "latest": "2026-11-21"},
                                    "origin": {"point": {"city": "Dallas", "state": "TX", "deadhead": {"miles": 15}}},
                                    "destination": {"point": {"city": "Atlanta", "state": "GA"}},
                                    "poster": {
                                        "company": "Acme Logistics",
                                        "city": "Dallas",
                                        "state": "TX",
                                        "contact": {"email": "desk@acme.test", "phone": {"number": "5550100"}},
                                    },
                                    "rate": {"baseRate": {"amount": 2100, "currency": "USD"}},
                                    "tripLength": {"distanceMiles": 800, "type": "ROAD"},
                                    "specs": {
                                        "requiredEquipmentType": "V",
                                        "requiredCapacity": "FULL",
                                        "lengthInFeet": 53,
                                        "weightInPounds": 42000,
                                    },
                                    "credit": {"score": 96, "daysToPay": 24},
                                    "comments": [{"comment": "No touch"}],
                                    "createdWhen": "2026-11-20T01:00:00Z",
                                }
                            ],
                        },
                    }
                }
            }

        with patch("server.load_board.post_graphql", side_effect=transport):
            # search_loads calls post_graphql unless a transport is passed.
            # The HTTP handler calls search_loads without a transport, so patch post_graphql.
            found = requests.post(
                self.base + "/api/v1/loads/search",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "origin": {"city": "Dallas", "state": "TX", "deadhead_miles": 100},
                    "destination": "Atlanta, GA",
                    "equipment": ["van"],
                    "capacity": "FULL",
                },
                timeout=10,
            )
        self.assertEqual(found.status_code, 200, found.text)
        body = found.json()
        self.assertEqual(body["search_id"], "search-9")
        self.assertEqual(body["count"], 1)
        load = body["loads"][0]
        self.assertEqual(load["id"], "lane+row-1")
        self.assertEqual(load["company"], "Acme Logistics")
        self.assertEqual(load["phone"], "5550100")
        self.assertEqual(load["email"], "desk@acme.test")
        self.assertEqual(load["rate"], 2100)
        self.assertEqual(load["rate_per_mile"], 2.62)
        self.assertEqual(load["miles"], 800)
        self.assertEqual(load["weight_lbs"], 42000)
        self.assertEqual(load["origin"]["city"], "Dallas")
        self.assertEqual(load["destination"]["city"], "Atlanta")
        self.assertEqual(load["comments"], ["No touch"])
        self.assertEqual(load["detail"]["postingId"], "P1")
        self.assertEqual(seen["token"], "eyJhbGci.payload.signature")
        criteria = seen["variables"]["createAndExecuteSearchCriteria"]["searchCriteria"]
        self.assertEqual(criteria["origin"]["point"]["city"], "Dallas")
        self.assertEqual(criteria["origin"]["point"]["deadhead"]["miles"], 100)
        self.assertEqual(criteria["destination"]["point"]["state"], "GA")
        self.assertEqual(criteria["desiredSpecs"]["equipmentClasses"], ["V"])
        self.assertNotIn("access_token", found.text)

        with patch("server.load_board.post_graphql", side_effect=transport):
            detail = requests.get(
                self.base + "/api/v1/loads/detail",
                headers={"X-API-Key": token},
                params={"search_id": "search-9", "match_id": "lane+row-1"},
                timeout=10,
            )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["dot"]["broker_mc"], "123456")
        self.assertEqual(detail.json()["peer_rating"]["average"], 4.5)
        self.assertEqual(detail.json()["detail"]["dotIds"]["dotNumber"], "999")

    def test_search_without_a_board_session_is_refused(self) -> None:
        create_account("dispatcher", "secret1", "day_1")
        token = self._token()
        response = requests.post(
            self.base + "/api/v1/loads/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"origin": {"city": "Dallas", "state": "TX"}},
            timeout=10,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("board session", response.json()["error"])

    def test_admin_cookie_login_still_works(self) -> None:
        session = requests.Session()
        login = session.post(
            self.base + "/admin/api/login",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        self.assertEqual(login.status_code, 200, login.text)
        users = session.get(self.base + "/admin/api/users", timeout=10)
        self.assertEqual(users.status_code, 200, users.text)
        self.assertTrue(users.json()["ok"])
