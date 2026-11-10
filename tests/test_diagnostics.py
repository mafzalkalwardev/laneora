"""White-screen diagnostics, connection checks, and lightweight startup flags."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app.client_log import client_log, redact_text
from app.connection_test import Check, advice, check_url, format_report, proxy_dict, run_checks
from app.runtime_mode import chromium_flags, lightweight_enabled, save_settings, software_rendering_enabled


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"x" * 80_000
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


class RedactionTest(unittest.TestCase):
    def test_log_drops_secrets_and_query_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch("app.client_log.log_dir", return_value=folder):
                client_log(
                    "load-failed",
                    url="https://user:hunter2@login.dat.com/u/login?state=SECRET&code=ABC",
                    password="hunter2",
                    cookie="session=abc",
                    proxy="none",
                )
                text = (folder / "laneora.log").read_text(encoding="utf-8")
        self.assertIn("load-failed", text)
        self.assertIn("login.dat.com", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("session=abc", text)
        self.assertNotIn("state=", text)
        self.assertIn("proxy=none", text)

    def test_redact_text_strips_userinfo(self) -> None:
        self.assertNotIn("s3cret", redact_text("http://admin:s3cret@proxy.example:8080/path"))


class ConnectionAdviceTest(unittest.TestCase):
    def test_proxy_failure_is_called_out(self) -> None:
        checks = [
            Check("one.dat.com", True, "HTTP 200, first byte 20 ms, sample 1 KB at 10 KB/s", "direct"),
            Check("proxy", True, "configured host proxy.example", "info"),
            Check("one.dat.com", False, "no answer (ProxyError)", "proxy"),
        ]
        self.assertIn("likely the proxy", advice(checks))
        report = format_report(checks)
        self.assertIn("PASS", report)
        self.assertIn("FAIL via proxy", report)
        self.assertNotIn("password", report)

    def test_direct_failure_points_at_the_network(self) -> None:
        checks = [Check("one.dat.com", False, "no answer (ConnectTimeout)", "direct")]
        self.assertIn("cannot reach DAT", advice(checks))

    def test_all_clear_points_at_graphics(self) -> None:
        checks = [
            Check("one.dat.com", True, "HTTP 200, first byte 20 ms, sample 1 KB at 10 KB/s", "direct"),
            Check("proxy", True, "not configured; this PC connects directly", "info"),
        ]
        self.assertIn("lightweight mode", advice(checks))

    def test_local_server_passes_and_closed_port_fails(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{httpd.server_address[1]}/sample"
            passed = check_url(base, timeout=3)
            self.assertTrue(passed.ok)
            self.assertIn("first byte", passed.detail)
            self.assertIn("KB/s", passed.detail)
            failed = check_url("http://127.0.0.1:1/", timeout=1)
            self.assertFalse(failed.ok)
            checks = run_checks(proxy_host="127.0.0.1", proxy_port=1, urls=(base,), timeout=1)
            self.assertTrue(any(item.group == "direct" and item.ok for item in checks))
            self.assertTrue(any(item.group == "proxy" and not item.ok for item in checks))
            self.assertNotIn("password", format_report(checks))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_proxy_dict_omits_password_from_the_public_shape_only_inside_url(self) -> None:
        proxies = proxy_dict("proxy.example", 8080, "user", "s3cret")
        assert proxies is not None
        self.assertIn("s3cret", proxies["http"])
        self.assertIsNone(proxy_dict("none", 0, "user", "s3cret"))


class RuntimeModeTest(unittest.TestCase):
    def test_flags_and_settings(self) -> None:
        self.assertEqual(chromium_flags("--no-sandbox", software=False), "--no-sandbox")
        self.assertEqual(
            chromium_flags("--no-sandbox", software=True),
            "--no-sandbox --disable-gpu --disable-gpu-compositing",
        )
        self.assertEqual(
            chromium_flags("--disable-gpu --no-sandbox", software=True),
            "--disable-gpu --no-sandbox --disable-gpu-compositing",
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch("app.runtime_mode.log_dir", return_value=folder):
                self.assertFalse(lightweight_enabled([]))
                save_settings(lightweight=True, software_rendering=True)
                self.assertTrue(lightweight_enabled([]))
                self.assertTrue(software_rendering_enabled([]))
                saved = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["lightweight"])
        self.assertTrue(software_rendering_enabled(["--software-rendering"]))
        self.assertTrue(lightweight_enabled(["--lightweight"]))


class SelfCheckTest(unittest.TestCase):
    def test_self_check_exits_before_the_window(self) -> None:
        import sys

        from app.main import start

        old = sys.argv
        sys.argv = ["Laneora", "--self-check"]
        try:
            with self.assertRaises(SystemExit) as raised:
                start()
            self.assertEqual(raised.exception.code, 0)
        finally:
            sys.argv = old


if __name__ == "__main__":
    unittest.main()
