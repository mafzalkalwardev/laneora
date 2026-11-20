"""Bearer-token HTTP API on the Soft server."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from server.soft_shim import Handler


class PublicApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "local_users.json").write_text('{"users": []}\n', encoding="utf-8")
        (root / "users.json").write_text('{"users": []}\n', encoding="utf-8")
        self.cfg_path = root / "soft_config.json"
        self.patches = [
            patch("server.soft_admin_lib.LOCAL_USERS_FILE", root / "local_users.json"),
            patch("server.soft_admin_lib.SOFT_CONFIG_FILE", self.cfg_path),
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
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["token_type"], "Bearer")
        self.assertTrue(body["token"])
        return body["token"]

    def test_index_health_and_cors_need_no_token(self) -> None:
        index = requests.get(self.base + "/api/v1", timeout=10)
        self.assertEqual(index.status_code, 200, index.text)
        body = index.json()
        self.assertEqual(body["service"], "laneora")
        self.assertIn("Authorization: Bearer", body["auth"])
        self.assertTrue(any(route["path"] == "/api/v1/users" for route in body["routes"]))
        self.assertEqual(index.headers["Access-Control-Allow-Origin"], "*")
        self.assertNotIn("token", body)

        health = requests.get(self.base + "/api/v1/health", timeout=10)
        self.assertEqual(health.status_code, 200, health.text)
        self.assertTrue(health.json()["ok"])
        self.assertEqual(health.json()["accounts"], 0)

        options = requests.options(self.base + "/api/v1/users", timeout=10)
        self.assertEqual(options.status_code, 204, options.text)
        self.assertIn("PATCH", options.headers["Access-Control-Allow-Methods"])
        self.assertIn("Authorization", options.headers["Access-Control-Allow-Headers"])

    def test_session_rejects_a_bad_password_and_accounts_require_the_token(self) -> None:
        bad = requests.post(
            self.base + "/api/v1/session",
            json={"username": "admin", "password": "nope"},
            timeout=10,
        )
        self.assertEqual(bad.status_code, 401, bad.text)

        missing = requests.get(self.base + "/api/v1/users", timeout=10)
        self.assertEqual(missing.status_code, 401, missing.text)
        wrong = requests.get(
            self.base + "/api/v1/users",
            headers={"Authorization": "Bearer not-the-token"},
            timeout=10,
        )
        self.assertEqual(wrong.status_code, 401, wrong.text)

    def test_bearer_and_api_key_manage_an_account(self) -> None:
        token = self._token()
        again = self._token()
        self.assertEqual(token, again)
        headers = {"Authorization": f"Bearer {token}"}

        created = requests.post(
            self.base + "/api/v1/users",
            headers=headers,
            json={"username": "ada", "password": "secret1", "plan": "day_1"},
            timeout=10,
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["user"]["services"], ["dat"])
        self.assertEqual(created.json()["user"]["password"], "secret1")
        self.assertNotIn("streams", created.json()["user"])

        listed = requests.get(self.base + "/api/v1/users", headers={"X-API-Key": token}, timeout=10)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["summary"]["total"], 1)
        self.assertEqual(listed.json()["users"][0]["username"], "ada")

        one = requests.get(self.base + "/api/v1/users/ada", headers=headers, timeout=10)
        self.assertEqual(one.status_code, 200, one.text)
        self.assertEqual(one.json()["user"]["plan"], "day_1")

        patched = requests.patch(
            self.base + "/api/v1/users/ada",
            headers=headers,
            json={"plan": "week_1", "extend": True, "services": ["dat_dual", "dat"]},
            timeout=10,
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["user"]["services"], ["dat", "dat_dual"])
        self.assertEqual(patched.json()["user"]["plan"], "week_1")

        catalog = requests.get(self.base + "/api/v1/catalog", headers=headers, timeout=10)
        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertIn("dat_4", [item["id"] for item in catalog.json()["services"]])

        missing = requests.get(self.base + "/api/v1/users/nobody", headers=headers, timeout=10)
        self.assertEqual(missing.status_code, 404, missing.text)

        removed = requests.delete(self.base + "/api/v1/users/ada", headers=headers, timeout=10)
        self.assertEqual(removed.status_code, 200, removed.text)
        gone = requests.get(self.base + "/api/v1/users/ada", headers=headers, timeout=10)
        self.assertEqual(gone.status_code, 404, gone.text)

        auth = requests.get(
            self.base + "/authenticate",
            params={"username": "ada", "key": "secret1", "value": "1", "is_alive": "1"},
            timeout=10,
        )
        self.assertEqual(auth.status_code, 200)
        self.assertEqual(auth.text, "0")

    def test_rotate_replaces_the_token(self) -> None:
        token = self._token()
        rotated = requests.post(
            self.base + "/api/v1/token/rotate",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        fresh = rotated.json()["token"]
        self.assertNotEqual(fresh, token)
        old = requests.get(self.base + "/api/v1/users", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        self.assertEqual(old.status_code, 401, old.text)
        new = requests.get(self.base + "/api/v1/users", headers={"Authorization": f"Bearer {fresh}"}, timeout=10)
        self.assertEqual(new.status_code, 200, new.text)

    def test_env_token_is_used_and_rotate_is_refused(self) -> None:
        with patch.dict(os.environ, {"LANEORA_API_TOKEN": "fixed-token-value"}):
            issued = self._token()
            self.assertEqual(issued, "fixed-token-value")
            refused = requests.post(
                self.base + "/api/v1/token/rotate",
                headers={"Authorization": "Bearer fixed-token-value"},
                timeout=10,
            )
            self.assertEqual(refused.status_code, 400, refused.text)

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
