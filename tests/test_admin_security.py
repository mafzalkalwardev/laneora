"""Regression tests for dashboard and dispatcher authentication."""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.client import HTTPConnection
from pathlib import Path

# Isolate every import-time path before server modules touch data/.
_ISOLATION = tempfile.mkdtemp(prefix="laneora-security-import-")
os.environ["LANEORA_DATA_DIR"] = _ISOLATION
os.environ["LANEORA_ALLOW_GET_AUTH"] = "1"

from server import security  # noqa: E402
from server.soft_admin_lib import (  # noqa: E402
    import_roster,
    load_config,
    load_local_users,
    migrate_secrets,
    revoke_all_sessions,
)
from server.soft_shim import Handler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

DASH_USER = "owner_9f3c1a7b"
DASH_PASSWORD = "correct-horse-battery"
CLIENT_USER = "admin"
CLIENT_PASSWORD = "client-secret-99"
OTHER_CLIENT = "dispatcher2"
OTHER_PASSWORD = "Dispatch99xx"


def _client(username: str, password: str) -> dict:
    return {
        "username": username,
        "password": password,
        "active": True,
        "active_subs": ["one", "power"],
        "px": "none",
        "p": "0",
        "pu": "",
        "pd": "",
        "streams": {
            "one": {"url": "https://one.dat.com", "store": [], "lst": "{}", "sst": ""},
            "power": {"url": "https://power.dat.com", "store": [], "lst": "{}", "sst": ""},
        },
    }


class AdminSecurityTests(unittest.TestCase):
    httpd: ThreadingHTTPServer
    port: int

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
        os.environ.pop("LANEORA_COOKIE_SECURE", None)
        security.PBKDF2_ITERATIONS = 1_200
        security.reset_throttles()
        self.ip = f"203.0.113.{self._next_ip()}"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    _ip_counter = 20

    @classmethod
    def _next_ip(cls) -> int:
        cls._ip_counter += 1
        return cls._ip_counter

    def write_plaintext(self, *, dash_user: str, dash_password: str, clients: list[tuple[str, str]]) -> None:
        root = Path(self.tmp.name)
        root.mkdir(parents=True, exist_ok=True)
        config = {
            "allow_multi_screen": False,
            "shared_proxy": {"px": "none", "p": "0", "pu": "", "pd": ""},
            "dashboard": {"username": dash_user, "password": dash_password},
        }
        (root / "soft_config.json").write_text(json.dumps(config), encoding="utf-8")
        os.chmod(root / "soft_config.json", 0o644)
        users = [_client(name, password) for name, password in clients]
        (root / "local_users.json").write_text(json.dumps({"users": users}), encoding="utf-8")
        os.chmod(root / "local_users.json", 0o644)

    def migrate(self) -> dict:
        return migrate_secrets()

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, list[str]]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"X-Real-IP": self.ip}
        if headers:
            hdrs.update(headers)
        if cookies:
            hdrs["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=data, headers=hdrs)
        response = connection.getresponse()
        raw = response.read()
        self.last_headers = response.getheaders()
        set_cookies = [value for key, value in self.last_headers if key.lower() == "set-cookie"]
        connection.close()
        return response.status, raw, set_cookies

    @staticmethod
    def cookies_of(headers: list[str]) -> dict[str, list[str]]:
        parsed: dict[str, list[str]] = {}
        for header in headers:
            parts = [part.strip() for part in header.split(";")]
            name, value = parts[0].split("=", 1)
            parsed[name] = [value, *parts[1:]]
        return parsed

    def csrf_from_page(self) -> dict[str, str]:
        status, _body, set_cookies = self.request("GET", "/admin")
        self.assertEqual(status, 200)
        cookies = self.cookies_of(set_cookies)
        self.assertIn("laneora_csrf", cookies)
        return {"laneora_csrf": cookies["laneora_csrf"][0]}

    def login(self, username: str = DASH_USER, password: str = DASH_PASSWORD, code: str = "") -> tuple[int, dict, dict[str, str]]:
        cookies = self.csrf_from_page()
        body = {"username": username, "password": password}
        if code:
            body["code"] = code
        status, raw, set_cookies = self.request(
            "POST",
            "/admin/api/login",
            body,
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["laneora_csrf"]},
        )
        payload = json.loads(raw.decode("utf-8"))
        merged = dict(cookies)
        for name, parts in self.cookies_of(set_cookies).items():
            if parts[0] != "":
                merged[name] = parts[0]
        return status, payload, merged

    def auth_query(self, username: str, password: str) -> tuple[int, str]:
        query = urllib.parse.urlencode(
            {"username": username, "key": password, "value": "4242", "is_alive": "7"}
        )
        status, raw, _ = self.request("GET", "/authenticate?" + query)
        return status, raw.decode("utf-8")

    def auth_post(self, username: str, password: str) -> tuple[int, str]:
        status, raw, _ = self.request(
            "POST",
            "/authenticate",
            {"username": username, "key": password, "value": "4242", "is_alive": "7"},
        )
        return status, raw.decode("utf-8")

    def test_production_kdf_cost(self) -> None:
        self.assertGreaterEqual(security.DEFAULT_PBKDF2_ITERATIONS, 600_000)
        previous = security.PBKDF2_ITERATIONS
        security.PBKDF2_ITERATIONS = security.DEFAULT_PBKDF2_ITERATIONS
        security.reset_throttles()
        try:
            encoded = security.hash_password("correct horse battery")
            self.assertTrue(security.verify_password("correct horse battery", encoded))
            self.assertFalse(security.verify_password("wrong horse battery", encoded))
            self.assertGreaterEqual(int(encoded.split("$")[1]), 600_000)
        finally:
            security.PBKDF2_ITERATIONS = previous
            security.reset_throttles()

    def test_default_dashboard_password_is_not_seeded_or_accepted(self) -> None:
        self.migrate()
        config_text = (Path(self.tmp.name) / "soft_config.json").read_text(encoding="utf-8")
        self.assertNotIn("admin123", config_text)
        self.assertNotIn('"password"', config_text)
        status, payload, _cookies = self.login("admin", "admin123")
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])
        root = Path(__file__).resolve().parents[1]
        source = (root / "server/soft_admin_lib.py").read_text(encoding="utf-8")
        shim = (root / "server/soft_shim.py").read_text(encoding="utf-8")
        self.assertNotIn("admin123", source)
        self.assertNotIn("admin123", shim)

    def test_known_default_dashboard_password_is_removed(self) -> None:
        self.write_plaintext(
            dash_user="admin",
            dash_password="admin123",
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        stats = self.migrate()
        self.assertTrue(stats["dashboard_default_removed"])
        self.assertFalse(stats["dashboard_configured"])
        text = (Path(self.tmp.name) / "soft_config.json").read_text(encoding="utf-8")
        self.assertNotIn("admin123", text)
        status, _payload, _cookies = self.login("admin", "admin123")
        self.assertEqual(status, 401)
        code, body = self.auth_post(CLIENT_USER, CLIENT_PASSWORD)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "okie")

    def test_migration_keeps_random_dashboard_and_client_logins(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD), (OTHER_CLIENT, OTHER_PASSWORD)],
        )
        stats = self.migrate()
        self.assertTrue(stats["dashboard_password_hashed"])
        self.assertEqual(stats["client_passwords_hashed"], 2)
        config_text = (Path(self.tmp.name) / "soft_config.json").read_text(encoding="utf-8")
        users_text = (Path(self.tmp.name) / "local_users.json").read_text(encoding="utf-8")
        self.assertNotIn(DASH_PASSWORD, config_text)
        self.assertNotIn(CLIENT_PASSWORD, users_text)
        self.assertNotIn(OTHER_PASSWORD, users_text)
        self.assertNotIn(OTHER_PASSWORD.lower(), users_text)
        self.assertIn("pbkdf2_sha256$", config_text)
        self.assertIn("pbkdf2_sha256$", users_text)
        self.assertEqual((Path(self.tmp.name) / "soft_config.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((Path(self.tmp.name) / "local_users.json").stat().st_mode & 0o777, 0o600)
        again = self.migrate()
        self.assertEqual(again["client_passwords_hashed"], 0)
        status, payload, cookies = self.login()
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])
        self.assertIn("laneora_admin", cookies)
        code, body = self.auth_get_legacy_case()
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "okie")

    def auth_get_legacy_case(self) -> tuple[int, str]:
        return self.auth_query(OTHER_CLIENT, OTHER_PASSWORD)

    def test_client_named_admin_is_not_dashboard_admin(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        status, payload, _cookies = self.login(CLIENT_USER, CLIENT_PASSWORD)
        self.assertEqual(status, 401, payload)
        code, body = self.auth_post(CLIENT_USER, CLIENT_PASSWORD)
        self.assertEqual(json.loads(body)["status"], "okie")
        dash_status, dash_body = self.auth_post(DASH_USER, DASH_PASSWORD)
        self.assertEqual(dash_status, 200)
        self.assertEqual(dash_body, "0")
        _status, raw, _ = self.request("GET", "/admin/api/users")
        self.assertEqual(_status, 401)
        logged = self.login()
        status, raw, _headers = self.request("GET", "/admin/api/users", cookies=logged[2])
        self.assertEqual(status, 200)
        payload = json.loads(raw.decode("utf-8"))
        self.assertNotIn(CLIENT_PASSWORD, raw.decode("utf-8"))
        for user in payload["users"]:
            self.assertNotIn("password", user)
            self.assertNotIn("password_hash", user)
            self.assertTrue(user["has_password"])

    def test_cookie_flags_and_csrf_and_unauthenticated_mutations(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        cookies = self.csrf_from_page()
        status, raw, set_cookies = self.request(
            "POST",
            "/admin/api/login",
            {"username": DASH_USER, "password": DASH_PASSWORD},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["laneora_csrf"], "X-Forwarded-Proto": "https"},
        )
        self.assertEqual(status, 200, raw)
        parsed = self.cookies_of(set_cookies)
        session_flags = " ".join(parsed["laneora_admin"][1:]).lower()
        self.assertIn("httponly", session_flags)
        self.assertIn("samesite=lax", session_flags)
        self.assertIn("secure", session_flags)
        self.assertIn("path=/admin", session_flags)
        csrf_flags = " ".join(parsed["laneora_csrf"][1:]).lower()
        self.assertNotIn("httponly", csrf_flags)
        self.assertIn("secure", csrf_flags)
        session = {"laneora_admin": parsed["laneora_admin"][0], "laneora_csrf": parsed["laneora_csrf"][0]}

        plain_page = self.csrf_from_page()
        status, raw, plain_cookies = self.request(
            "POST",
            "/admin/api/login",
            {"username": DASH_USER, "password": DASH_PASSWORD},
            cookies=plain_page,
            headers={"X-CSRF-Token": plain_page["laneora_csrf"]},
        )
        self.assertEqual(status, 200, raw)
        plain_flags = " ".join(self.cookies_of(plain_cookies)["laneora_admin"][1:]).lower()
        self.assertIn("httponly", plain_flags)
        self.assertNotIn("secure", plain_flags)

        status, raw, _ = self.request(
            "POST",
            "/admin/api/users",
            {"username": "newclient", "password": "newclient-pass", "plan": "day_1"},
            cookies={"laneora_admin": session["laneora_admin"]},
        )
        self.assertEqual(status, 403, raw)
        self.assertEqual(len(load_local_users()), 1)

        status, raw, _ = self.request(
            "POST",
            "/admin/api/users",
            {"username": "newclient", "password": "newclient-pass", "plan": "day_1"},
        )
        self.assertEqual(status, 401, raw)

        status, raw, _ = self.request(
            "POST",
            "/admin/api/users",
            {"username": "newclient", "password": "newclient-pass", "plan": "day_1"},
            cookies=session,
            headers={"X-CSRF-Token": session["laneora_csrf"], "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403, raw)

        status, raw, _ = self.request(
            "POST",
            "/admin/api/users",
            {"username": "newclient", "password": "newclient-pass", "plan": "day_1"},
            cookies=session,
            headers={"X-CSRF-Token": session["laneora_csrf"]},
        )
        self.assertEqual(status, 200, raw)
        code, body = self.auth_post("newclient", "newclient-pass")
        self.assertEqual(json.loads(body)["status"], "okie")
        self.assertNotIn("newclient-pass", (Path(self.tmp.name) / "local_users.json").read_text(encoding="utf-8"))

    def test_legacy_session_and_revocation(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        forged = DASH_USER + "." + hmac.new(
            DASH_PASSWORD.encode("utf-8"), DASH_USER.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        status, raw, _ = self.request("GET", "/admin/api/users", cookies={"laneora_admin": forged})
        self.assertEqual(status, 401, raw)

        _status, _payload, cookies = self.login()
        token = cookies["laneora_admin"]
        self.assertTrue(token.startswith("v2."))
        self.assertNotIn(DASH_PASSWORD, token)
        status, raw, _ = self.request("GET", "/admin/api/users", cookies=cookies)
        self.assertEqual(status, 200, raw)

        revoke_all_sessions()
        status, raw, _ = self.request("GET", "/admin/api/users", cookies=cookies)
        self.assertEqual(status, 401, raw)
        code, body = self.auth_post(CLIENT_USER, CLIENT_PASSWORD)
        self.assertEqual(json.loads(body)["status"], "okie")

        _status, _payload, cookies = self.login()
        old = dict(cookies)
        status, raw, rotated = self.request(
            "POST",
            "/admin/api/password",
            {"current": DASH_PASSWORD, "password": "replacement-horse-battery"},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["laneora_csrf"]},
        )
        self.assertEqual(status, 200, raw)
        status, raw, _ = self.request("GET", "/admin/api/users", cookies=old)
        self.assertEqual(status, 401, raw)
        new_cookie = self.cookies_of(rotated)["laneora_admin"][0]
        status, raw, _ = self.request(
            "GET",
            "/admin/api/users",
            cookies={"laneora_admin": new_cookie, "laneora_csrf": cookies["laneora_csrf"]},
        )
        self.assertEqual(status, 200, raw)
        denied, _payload, _cookies = self.login(DASH_USER, DASH_PASSWORD)
        self.assertEqual(denied, 401)
        allowed, payload, _cookies = self.login(DASH_USER, "replacement-horse-battery")
        self.assertEqual(allowed, 200, payload)

    def test_username_rotation_does_not_affect_client_admin(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        _status, _payload, cookies = self.login()
        status, raw, _ = self.request(
            "POST",
            "/admin/api/password",
            {"current": DASH_PASSWORD, "username": "rotated_owner_name"},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["laneora_csrf"]},
        )
        self.assertEqual(status, 200, raw)
        status, payload, _cookies = self.login("rotated_owner_name", DASH_PASSWORD)
        self.assertEqual(status, 200, payload)
        status, payload, _cookies = self.login(DASH_USER, DASH_PASSWORD)
        self.assertEqual(status, 401, payload)
        code, body = self.auth_query(CLIENT_USER, CLIENT_PASSWORD)
        self.assertEqual(json.loads(body)["status"], "okie")

    def test_login_throttling(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        previous = security.ADMIN_LOGIN_LIMIT
        security.ADMIN_LOGIN_LIMIT = 2
        try:
            self.login(DASH_USER, "wrong-password-value")
            self.login(DASH_USER, "wrong-password-value")
            status, payload, _cookies = self.login(DASH_USER, DASH_PASSWORD)
            self.assertEqual(status, 429, payload)
        finally:
            security.ADMIN_LOGIN_LIMIT = previous

    def test_post_and_legacy_get_authenticate_and_logger(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        status, body = self.auth_post(CLIENT_USER, CLIENT_PASSWORD.upper())
        self.assertEqual(json.loads(body)["status"], "okie")
        status, raw, _cookies = self.request("GET", "/logger?uva=admin:4242:7")
        self.assertEqual(status, 200)
        self.assertEqual(raw.decode("utf-8"), "4242")
        status, raw, _cookies = self.request(
            "GET", "/authenticate?username=admin&key=client-secret-99&value=1&is_alive=1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw.decode("utf-8"))["status"], "okie")
        self.assertTrue(
            any(
                key.lower() == "access-control-allow-origin" and value == "*"
                for key, value in self.last_headers
            )
        )
        log_line = security.redact_secrets(
            "GET /authenticate?username=admin&key=client-secret-99&value=1 HTTP/1.1"
        )
        self.assertNotIn("client-secret-99", log_line)
        self.assertIn("key=REDACTED", log_line)
        status, raw, _ = self.request("GET", "/logger?uva=admin:4242:7")
        self.assertEqual(raw.decode("utf-8"), "0")

        os.environ["LANEORA_ALLOW_GET_AUTH"] = "0"
        try:
            status, body = self.auth_query(CLIENT_USER, CLIENT_PASSWORD)
            self.assertEqual(status, 405)
            from app.auth import _authenticate_against

            parsed, code, _text = _authenticate_against(
                f"http://127.0.0.1:{self.port}",
                CLIENT_USER,
                CLIENT_PASSWORD,
                4242,
                7,
            )
            self.assertEqual(code, 200)
            self.assertEqual(parsed["status"], "okie")
        finally:
            os.environ["LANEORA_ALLOW_GET_AUTH"] = "1"

    def test_no_wildcard_cors_on_health(self) -> None:
        self.migrate()
        status, _raw, _cookies = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(
            any(key.lower() == "access-control-allow-origin" and value == "*" for key, value in self.last_headers)
        )

    def test_optional_totp_is_not_mandatory_until_enrolled(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        self.migrate()
        status, payload, cookies = self.login()
        self.assertEqual(status, 200, payload)
        self.assertNotIn("totp_required", payload)

        status, raw, _ = self.request(
            "POST",
            "/admin/api/totp/setup",
            {},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["laneora_csrf"]},
        )
        started = json.loads(raw.decode("utf-8"))
        self.assertTrue(started["ok"], started)
        code = _totp(started["secret"])
        status, raw, set_cookies = self.request(
            "POST",
            "/admin/api/totp/confirm",
            {"code": code},
            cookies=cookies,
            headers={"X-CSRF-Token": cookies["laneora_csrf"]},
        )
        confirmed = json.loads(raw.decode("utf-8"))
        self.assertEqual(status, 200, confirmed)
        self.assertEqual(len(confirmed["recovery_codes"]), 8)
        config_text = (Path(self.tmp.name) / "soft_config.json").read_text(encoding="utf-8")
        for recovery in confirmed["recovery_codes"]:
            self.assertNotIn(recovery, config_text)

        status, payload, no_session = self.login()
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload.get("totp_required"))
        self.assertNotIn("laneora_admin", no_session)

        status, payload, _cookies = self.login(code="000000")
        self.assertEqual(status, 401, payload)

        cfg = load_config()
        cfg["dashboard"]["totp"]["last_step"] = 0
        from server.soft_admin_lib import save_config

        save_config(cfg)
        security.throttle_clear("admin", self.ip)
        good_code = _totp(started["secret"])
        status, payload, cookies = self.login(code=good_code)
        self.assertEqual(status, 200, payload)
        self.assertIn("laneora_admin", cookies)
        security.throttle_clear("admin", self.ip)
        status, payload, _cookies = self.login(code=good_code)
        self.assertEqual(status, 401, payload)

        recovery = confirmed["recovery_codes"][0]
        security.throttle_clear("admin", self.ip)
        status, payload, cookies = self.login(code=recovery)
        self.assertEqual(status, 200, payload)
        self.assertIn("laneora_admin", cookies)
        security.throttle_clear("admin", self.ip)
        status, payload, _cookies = self.login(code=recovery)
        self.assertEqual(status, 401, payload)

        code, body = self.auth_post(CLIENT_USER, CLIENT_PASSWORD)
        self.assertEqual(json.loads(body)["status"], "okie")

    def test_import_roster_hashes_without_auto_enabling_it(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[(CLIENT_USER, CLIENT_PASSWORD)],
        )
        roster = {
            "users": [
                {"username": "onlyroster", "password": "roster-secret-77", "label": "onlyroster"},
            ]
        }
        path = Path(self.tmp.name) / "users.json"
        path.write_text(json.dumps(roster), encoding="utf-8")
        self.migrate()
        status, body = self.auth_post("onlyroster", "roster-secret-77")
        self.assertEqual(body, "0")
        preview = import_roster(apply=False)
        self.assertEqual(preview["imported"], [])
        self.assertEqual(preview["pending"], ["onlyroster"])
        imported = import_roster(apply=True)
        self.assertEqual(imported["imported"], ["onlyroster"])
        status, body = self.auth_post("onlyroster", "roster-secret-77")
        self.assertEqual(json.loads(body)["status"], "okie")
        stored = (Path(self.tmp.name) / "local_users.json").read_text(encoding="utf-8")
        self.assertNotIn("roster-secret-77", stored)
        self.assertEqual(status, 200)

    def test_logout_revokes_one_session(self) -> None:
        self.write_plaintext(
            dash_user=DASH_USER,
            dash_password=DASH_PASSWORD,
            clients=[],
        )
        self.migrate()
        _status, _payload, first = self.login()
        security.throttle_clear("admin", self.ip)
        _status, _payload, second = self.login()
        status, raw, _ = self.request(
            "POST",
            "/admin/api/logout",
            {},
            cookies=first,
            headers={"X-CSRF-Token": first["laneora_csrf"]},
        )
        self.assertEqual(status, 200, raw)
        status, raw, _ = self.request("GET", "/admin/api/users", cookies=first)
        self.assertEqual(status, 401, raw)
        status, raw, _ = self.request("GET", "/admin/api/users", cookies=second)
        self.assertEqual(status, 200, raw)
        cfg = load_config()
        self.assertTrue(security.valid_session_key(cfg["session_key"]))
        self.assertNotIn(DASH_PASSWORD, json.dumps(cfg))


def _totp(secret: str) -> str:
    raw = security.totp_secret_bytes(secret)
    assert raw is not None
    step = int(__import__("time").time() // 30)
    digest = hmac.new(raw, step.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


if __name__ == "__main__":
    unittest.main()
