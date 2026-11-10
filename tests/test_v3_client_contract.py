"""The shipped v3.0.0 binary only GETs /authenticate and parses the body.

Security headers and the password hash must not change that contract.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

_ISOLATION = tempfile.mkdtemp(prefix="laneora-v3-contract-")
os.environ["LANEORA_DATA_DIR"] = _ISOLATION
os.environ["LANEORA_ALLOW_GET_AUTH"] = "1"

from app import PASSPHRASE  # noqa: E402
from app.crypto_util import decrypt  # noqa: E402
from server import security  # noqa: E402
from server.soft_shim import Handler  # noqa: E402


def _v3_parse(raw: str):
    """app/auth.py as shipped in v3.0.0: body text only, GET already done."""
    text = (raw or "").strip()
    if text == "0":
        return 0
    return json.loads(text)


class V3ClientContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        security.PBKDF2_ITERATIONS = 1_200
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = int(cls.httpd.server_address[1])
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["LANEORA_DATA_DIR"] = self.tmp.name
        os.environ["LANEORA_ALLOW_GET_AUTH"] = "1"
        security.PBKDF2_ITERATIONS = 1_200
        security.reset_throttles()
        secret = "dispatch-secret"
        security.hash_client_password(secret)
        user = {
            "username": "shayan",
            "password_hash": security.hash_client_password(secret),
            "active": True,
            "active_subs": ["one", "power"],
            "px": "none",
            "p": "0",
            "pu": "",
            "pd": "",
            "streams": {
                "one": {
                    "url": "https://one.dat.com/search-loads",
                    "lst": "{}",
                    "sst": "",
                    "store": [
                        {
                            "name": "auth0",
                            "value": "must-not-appear-in-logs",
                            "domain": ".dat.com",
                            "path": "/",
                            "secure": True,
                            "httpOnly": True,
                            "expirationDate": 1_900_000_000,
                        }
                    ],
                }
            },
        }
        Path(self.tmp.name, "local_users.json").write_text(
            json.dumps({"users": [user]}), encoding="utf-8"
        )
        Path(self.tmp.name, "soft_config.json").write_text(
            json.dumps(
                {
                    "allow_multi_screen": False,
                    "shared_proxy": {"px": "none", "p": "0", "pu": "", "pd": ""},
                    "dashboard": {
                        "username": "owner_account",
                        "password_hash": security.hash_password("dashboard-secret-1"),
                    },
                    "session_key": security.new_session_key(),
                }
            ),
            encoding="utf-8",
        )
        self.secret = secret

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _get(self, path: str) -> tuple[int, bytes, list[tuple[str, str]]]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("GET", path, headers={"Accept": "application/json", "X-Real-IP": "203.0.113.50"})
        response = connection.getresponse()
        body = response.read()
        headers = response.getheaders()
        connection.close()
        return response.status, body, headers

    def test_shipped_get_authenticate_still_decrypts_for_the_webview(self) -> None:
        query = urlencode(
            {"username": "Shayan", "key": self.secret.upper(), "value": "4242", "is_alive": "7"}
        )
        status, body, headers = self._get("/authenticate?" + query)
        self.assertEqual(status, 200)
        header_map = {key.lower(): value for key, value in headers}
        self.assertEqual(header_map.get("access-control-allow-origin"), "*")
        self.assertNotIn("x-content-type-options", header_map)
        parsed = _v3_parse(body.decode("utf-8"))
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["status"], "okie")
        self.assertEqual(int(parsed["p"]), 0)
        self.assertEqual(str(parsed["px"]).strip().lower(), "none")
        self.assertNotIn("must-not-appear-in-logs", body.decode("utf-8"))
        stream = json.loads(decrypt(PASSPHRASE, parsed["one"]))
        self.assertIn("one.dat.com", str(stream["url"]))
        self.assertEqual(stream["store"][0]["name"], "auth0")
        self.assertEqual(stream["store"][0]["value"], "must-not-appear-in-logs")
        self.assertNotIn("password", parsed)

        logger_status, logger_body, _ = self._get("/logger?uva=shayan:4242:7")
        self.assertEqual(logger_status, 200)
        self.assertEqual(logger_body.decode("utf-8"), "4242")


if __name__ == "__main__":
    unittest.main()
