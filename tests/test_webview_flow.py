"""Blank-page decisions for the embedded view. Does not claim a DAT page rendered."""
from __future__ import annotations

import unittest

from app.webview_flow import cookie_origin, describe_navigation, on_load_event


class WebViewFlowTests(unittest.TestCase):
    def test_about_blank_is_ignored_and_not_reloaded(self) -> None:
        self.assertEqual(on_load_event("about:blank", True, False), "ignore")
        self.assertEqual(on_load_event("about:blank", False, False), "ignore")

    def test_real_navigation_reports_success_or_failure(self) -> None:
        url = "https://one.dat.com/search-loads"
        self.assertEqual(on_load_event(url, True, False), "inject")
        self.assertEqual(on_load_event(url, False, False), "fail")
        self.assertEqual(on_load_event(url, False, True), "ignore")

    def test_cookie_origin_is_never_empty(self) -> None:
        self.assertEqual(cookie_origin(".dat.com"), "https://dat.com/")
        self.assertEqual(cookie_origin(""), "https://one.dat.com/")

    def test_diag_line_has_result_and_no_cookie_value(self) -> None:
        line = describe_navigation(
            "https://one.dat.com/search-loads",
            "none",
            [{"name": "auth0", "value": "super-secret-token"}],
            ok=False,
        )
        self.assertIn("result=fail", line)
        self.assertIn("auth0=present", line)
        self.assertIn("cookies=1", line)
        self.assertNotIn("super-secret-token", line)


if __name__ == "__main__":
    unittest.main()
