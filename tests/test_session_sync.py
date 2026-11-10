"""Login cookies and auth tokens copy across a module; searches do not."""
from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage",
)

try:
    from PyQt5.QtCore import Qt, QEventLoop, QTimer, QUrl
    from PyQt5.QtNetwork import QNetworkCookie
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView
except Exception as exc:  # pragma: no cover - optional in bare checkouts
    QApplication = None  # type: ignore[misc, assignment]
    QEventLoop = QTimer = QUrl = QNetworkCookie = None  # type: ignore[misc, assignment]
    QWebEnginePage = QWebEngineProfile = QWebEngineView = None  # type: ignore[misc, assignment]
    _QT_IMPORT_ERROR = exc
else:
    _QT_IMPORT_ERROR = None

from app.session_sync import ProfileSessionSync


PAGE = """<!doctype html><title>{name}</title><p>{name}</p>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = PAGE.format(name=self.path.strip("/")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def _wait(app: QApplication, milliseconds: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec_()
    app.processEvents()


@unittest.skipIf(QApplication is None, f"PyQt5 is not installed: {_QT_IMPORT_ERROR}")
class SessionSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def _pair(self):
        left = QWebEngineView()
        right = QWebEngineView()
        left_profile = QWebEngineProfile(left)
        right_profile = QWebEngineProfile(right)
        left.setPage(QWebEnginePage(left_profile, left))
        right.setPage(QWebEnginePage(right_profile, right))
        sync = ProfileSessionSync()
        sync.watch(left_profile, left)
        sync.watch(right_profile, right)
        sync.note_opened(left_profile)
        sync.note_opened(right_profile)
        sync.enable_removals()
        return left, right, sync

    def test_refreshed_cookie_reaches_the_other_profile_only(self) -> None:
        left, right, sync = self._pair()
        try:
            left.load(QUrl(self.base + "/search-a"))
            right.load(QUrl(self.base + "/search-b"))
            _wait(self.app, 1500)
            self.assertTrue(left.url().toString().endswith("/search-a"))
            self.assertTrue(right.url().toString().endswith("/search-b"))

            seen: list[bytes] = []

            def grab(cookie: QNetworkCookie) -> None:
                if bytes(cookie.name()) in (b"auth_token", b"fromjs"):
                    seen.append(bytes(cookie.name()) + b"=" + bytes(cookie.value()))

            right.page().profile().cookieStore().cookieAdded.connect(grab)
            host = self.base.split("://", 1)[1].split("/", 1)[0]
            cookie = QNetworkCookie(b"auth_token", b"one")
            cookie.setDomain(host)
            cookie.setPath("/")
            left.page().profile().cookieStore().setCookie(cookie, QUrl(self.base))
            _wait(self.app, 800)
            self.assertIn(b"auth_token=one", seen)

            seen.clear()
            cookie = QNetworkCookie(b"auth_token", b"two")
            cookie.setDomain(host)
            cookie.setPath("/")
            left.page().profile().cookieStore().setCookie(cookie, QUrl(self.base))
            _wait(self.app, 800)
            self.assertIn(b"auth_token=two", seen)

            seen.clear()
            left.page().runJavaScript("document.cookie = 'fromjs=refreshed; path=/';")
            _wait(self.app, 800)
            self.assertIn(b"fromjs=refreshed", seen)
            self.assertTrue(left.url().toString().endswith("/search-a"))
            self.assertTrue(right.url().toString().endswith("/search-b"))
            self.assertEqual(sync.store_count, 2)
        finally:
            sync.close()
            left.deleteLater()
            right.deleteLater()
            self.app.processEvents()

    def test_auth_token_copies_and_search_storage_does_not(self) -> None:
        left, right, sync = self._pair()
        try:
            left.load(QUrl(self.base + "/left"))
            right.load(QUrl(self.base + "/right"))
            _wait(self.app, 1500)
            left.page().runJavaScript(
                "localStorage.setItem('laneora_filter', 'chicago');"
                "localStorage.setItem('@@auth0spajs@@::client', 'token-1');"
            )
            _wait(self.app, 200)
            sync.poll_tokens()
            _wait(self.app, 800)
            auth: list[str] = []
            search: list[str] = []
            loop = QEventLoop()

            def read_auth(value) -> None:
                auth.append("" if value is None else str(value))
                if len(auth) and len(search):
                    loop.quit()

            def read_search(value) -> None:
                search.append("" if value is None else str(value))
                if len(auth) and len(search):
                    loop.quit()

            right.page().runJavaScript("localStorage.getItem('@@auth0spajs@@::client')", read_auth)
            right.page().runJavaScript("localStorage.getItem('laneora_filter')", read_search)
            QTimer.singleShot(2000, loop.quit)
            loop.exec_()
            self.assertEqual(auth, ["token-1"])
            self.assertEqual(search, [""])

            left.page().runJavaScript("localStorage.setItem('@@auth0spajs@@::client', 'token-2');")
            _wait(self.app, 200)
            sync.poll_tokens()
            _wait(self.app, 800)
            refreshed: list[str] = []
            loop = QEventLoop()
            right.page().runJavaScript(
                "localStorage.getItem('@@auth0spajs@@::client')",
                lambda value: (refreshed.append("" if value is None else str(value)), loop.quit()),
            )
            QTimer.singleShot(2000, loop.quit)
            loop.exec_()
            self.assertEqual(refreshed, ["token-2"])
            self.assertTrue(left.url().toString().endswith("/left"))
            self.assertTrue(right.url().toString().endswith("/right"))
        finally:
            sync.close()
            left.deleteLater()
            right.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
