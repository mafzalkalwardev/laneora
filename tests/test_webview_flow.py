"""Blank-page decisions: about:blank is not DAT, and cookies need an origin."""
from __future__ import annotations

import unittest
from pathlib import Path

from app.webview_flow import cookie_origin, is_blank_url, on_load_event

ROOT = Path(__file__).resolve().parents[1]


class WebViewFlowTest(unittest.TestCase):
    def test_about_blank_is_not_a_loaded_page(self) -> None:
        self.assertTrue(is_blank_url(""))
        self.assertTrue(is_blank_url("about:blank"))
        self.assertFalse(is_blank_url("https://one.dat.com/search-loads"))
        self.assertEqual(on_load_event("about:blank", True, False), "ignore")
        self.assertEqual(on_load_event("", True, False), "ignore")
        self.assertEqual(on_load_event("https://one.dat.com/search-loads", True, False), "inject")
        self.assertEqual(on_load_event("https://one.dat.com/search-loads", False, False), "fail")
        self.assertEqual(on_load_event("https://one.dat.com/search-loads", True, True), "ignore")

    def test_cookie_origin_is_never_empty(self) -> None:
        self.assertEqual(cookie_origin(".login.dat.com"), "https://login.dat.com/")
        self.assertEqual(cookie_origin(""), "https://one.dat.com/")
        self.assertEqual(cookie_origin("one.dat.com"), "https://one.dat.com/")

    def test_session_is_not_wiped_and_cookies_get_an_origin(self) -> None:
        window = (ROOT / "app" / "window.py").read_text(encoding="utf-8")
        browser = (ROOT / "app" / "browser.py").read_text(encoding="utf-8")
        self.assertNotIn("deleteAllCookies()", window)
        self.assertNotIn("setCookie(qcookie, QUrl())", browser)
        self.assertIn("cookie_origin", browser)


if __name__ == "__main__":
    unittest.main()
