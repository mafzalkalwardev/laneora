"""Offscreen checks for the original DAT screen and the two-tab dual search module."""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox --disable-gpu --disable-dev-shm-usage",
)

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QPushButton, QToolBar

    # WebEngine has to be imported before the QApplication exists.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineView
except Exception as exc:  # pragma: no cover - optional in bare checkouts
    QApplication = None  # type: ignore[misc, assignment]
    QPushButton = QToolBar = QWebEngineProfile = QWebEngineView = None  # type: ignore[misc, assignment]
    _QT_IMPORT_ERROR = exc
else:
    _QT_IMPORT_ERROR = None

from app import PASSPHRASE
from app.auth import AuthSession
from app.crypto_util import encrypt
from app.services import DAT, DAT_3, DAT_4, DAT_DUAL


def _layout_buttons(window) -> list[str]:
    found: list[str] = []

    def walk(layout) -> None:
        if layout is None:
            return
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()
            if isinstance(widget, QPushButton):
                found.append(widget.text())
            if widget is not None and widget.layout() is not None:
                walk(widget.layout())
            if item.layout() is not None:
                walk(item.layout())

    walk(window.layout)
    return found


@unittest.skipIf(QApplication is None, f"PyQt5 is not installed: {_QT_IMPORT_ERROR}")
class WindowModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from app.window import MainWindow

        blob = encrypt(
            PASSPHRASE,
            json.dumps({"url": "https://one.dat.com", "store": [], "lst": "{}", "sst": ""}),
        )
        self.blob = blob
        self.base = {
            "status": "okie",
            "px": "none",
            "p": "0",
            "pu": "",
            "pd": "",
            "one": blob,
        }
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.app.processEvents()

    def test_dat_only_keeps_the_single_search_button(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, dict(self.base))
        self.window.session = session
        self.window.show_select_screen(session)
        self.assertEqual(_layout_buttons(self.window), ["Load DAT Stream", "Connection test"])

    def test_assigned_services_show_both_modules(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": "dat_dual,dat"})
        self.window.session = session
        self.window.show_select_screen(session)
        self.assertEqual(_layout_buttons(self.window), ["Load DAT Stream", "Dual DAT Search", "Connection test"])

    def test_picker_shows_only_the_modules_assigned_to_this_login(self) -> None:
        cases = {
            DAT_3: ["3 DAT Search", "Connection test"],
            DAT_4: ["4 DAT Search", "Connection test"],
            f"{DAT_4},{DAT_3}": ["3 DAT Search", "4 DAT Search", "Connection test"],
            f"{DAT},{DAT_DUAL},{DAT_3},{DAT_4}": [
                "Load DAT Stream",
                "Dual DAT Search",
                "3 DAT Search",
                "4 DAT Search",
                "Connection test",
            ],
        }
        for raw, expected in cases.items():
            session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": raw})
            self.window.session = session
            self.window.show_select_screen(session)
            self.assertEqual(_layout_buttons(self.window), expected, raw)

    def _assert_isolated_tabs(self, count: int, *, cache_capped: bool) -> None:
        self.assertIsNotNone(self.window.tabs)
        self.assertEqual(self.window.tabs.count(), count)
        self.assertEqual(
            [self.window.tabs.tabText(i) for i in range(count)],
            [f"Search {index}" for index in range(1, count + 1)],
        )
        self.assertFalse(self.window.tabs.tabBar().isHidden())
        views = [self.window.tabs.widget(i) for i in range(count)]
        self.assertTrue(all(isinstance(view, QWebEngineView) for view in views))
        profiles = [view.page().profile() for view in views]
        self.assertEqual(len({id(profile) for profile in profiles}), count)
        stores = [profile.cookieStore() for profile in profiles]
        self.assertEqual(len({id(store) for store in stores}), count)
        default = QWebEngineProfile.defaultProfile()
        for profile in profiles:
            self.assertTrue(profile.isOffTheRecord())
            self.assertIsNot(profile, default)
            if cache_capped:
                self.assertEqual(profile.httpCacheMaximumSize(), 32 * 1024 * 1024)
                self.assertEqual(profile.httpCacheType(), QWebEngineProfile.MemoryHttpCache)
            else:
                self.assertNotEqual(profile.httpCacheMaximumSize(), 32 * 1024 * 1024)

    def test_dual_search_opens_two_independent_tabs(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": DAT_DUAL})
        self.window.session = session
        self.window._services = [DAT_DUAL]
        self.window.browse_dual(self.blob, "none", 0, "", "", 0)
        self._assert_isolated_tabs(2, cache_capped=False)
        self.assertEqual(self.window.findChildren(QToolBar), [])
        self.assertEqual(self.window._session_sync.store_count, 2)

    def test_three_and_four_open_separate_profiles(self) -> None:
        session = AuthSession(
            "ada",
            "secret",
            1,
            1,
            {**self.base, "services": f"{DAT},{DAT_DUAL},{DAT_3},{DAT_4}"},
        )
        self.window.session = session
        self.window._services = [DAT, DAT_DUAL, DAT_3, DAT_4]
        self.window.open_service(DAT_3)
        self.assertEqual(self.window._open_mode, DAT_3)
        self._assert_isolated_tabs(3, cache_capped=True)
        self.assertEqual(self.window._session_sync.store_count, 3)
        self.app.processEvents()
        self.window.open_service(DAT_4)
        self.assertEqual(self.window._open_mode, DAT_4)
        self._assert_isolated_tabs(4, cache_capped=True)
        self.assertEqual(self.window._session_sync.store_count, 4)
        labels = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertIn("3 Search", labels)
        self.assertIn("4 Search", labels)
        self.assertIn("Dual Search", labels)
        self.assertIn("DAT Search", labels)
        self.assertNotIn("6 Search", labels)

    def test_original_module_still_hides_the_tab_bar(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": f"{DAT},{DAT_DUAL}"})
        self.window.session = session
        self.window._services = [DAT]
        self.window.browse(self.blob, "none", 0, "", "", "one", 0)
        self.assertEqual(self.window.tabs.count(), 1)
        self.assertTrue(self.window.tabs.tabBar().isHidden())
        self.assertEqual(self.window.tabs.tabText(0), "Screen")
        self.assertEqual(self.window.findChildren(QToolBar), [])

        self.window._services = [DAT, DAT_DUAL, DAT_3, DAT_4]
        self.window.browse(self.blob, "none", 0, "", "", "one", 0)
        self.assertEqual(self.window.tabs.count(), 1)
        self.assertTrue(self.window.tabs.tabBar().isHidden())
        self.assertEqual(self.window.tabs.tabText(0), "Screen")
        self.assertIsNone(self.window._session_sync)
        labels = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertIn("DAT Search", labels)
        self.assertIn("Dual Search", labels)
        self.assertIn("3 Search", labels)
        self.assertIn("4 Search", labels)

    def test_switching_modules_cancels_staggered_opens(self) -> None:
        from PyQt5.QtCore import QEventLoop, QTimer

        session = AuthSession(
            "ada",
            "secret",
            1,
            1,
            {**self.base, "services": f"{DAT},{DAT_4}"},
        )
        self.window.session = session
        self.window._services = [DAT, DAT_4]
        self.window.open_service(DAT_4)
        pending = list(self.window._search_timers)
        self.assertEqual(len(pending), 4)
        self.assertTrue(all(timer.isActive() for timer in pending))

        self.window.open_service(DAT)
        self.assertTrue(all(not timer.isActive() for timer in pending))
        self.assertEqual(self.window.tabs.count(), 1)
        self.assertEqual(self.window.tabs.tabText(0), "Screen")
        replacement = [timer for timer in self.window._search_timers if timer.isActive()]
        self.assertEqual(len(replacement), 1)

        loop = QEventLoop()
        QTimer.singleShot(2300, loop.quit)
        loop.exec_()
        self.assertEqual(self.window.tabs.count(), 1)
        self.assertTrue(self.window.tabs.tabBar().isHidden())
        self.assertEqual(self.window.tabs.tabText(0), "Screen")

        self.window.open_service(DAT_4)
        self.assertEqual(self.window.tabs.count(), 4)
        self.assertFalse(self.window.tabs.tabBar().isHidden())
        self.assertEqual(
            [self.window.tabs.tabText(i) for i in range(4)],
            ["Search 1", "Search 2", "Search 3", "Search 4"],
        )
        self.assertEqual(self.window._session_sync.store_count, 4)
        self.assertFalse(self.window._session_sync.closed)

    def test_blank_page_shows_the_reason_retry_and_log(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        session = AuthSession("ada", "secret", 1, 1, dict(self.base))
        self.window.session = session
        self.window._services = [DAT]
        self.window.browse(self.blob, "none", 0, "", "", "one", 0)
        self.assertEqual(self.window._note_load_result(self.window.browser, True, "Screen"), "ignore")
        self.assertNotIn(id(self.window.browser), self.window._loaded_ids)
        self.assertIsNone(self.window._banner)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch("app.client_log.log_dir", return_value=folder), patch(
                "app.runtime_mode.log_dir", return_value=folder
            ):
                self.window._on_load_timeout(self.window.browser, "Screen")
                self.assertIsNotNone(self.window._banner)
                self.assertIn("DAT session was not applied", self.window._banner_text.text())
                self.assertIn("no site address", self.window._banner_text.text())
                self.window._note_load_result(self.window.browser, False, "Screen")
                self.assertIsNotNone(self.window._banner)
                self.assertIn("blank page", self.window._banner_text.text())
                self.assertIn(str(folder / "laneora.log"), self.window._banner_text.text())
                labels = [button.text() for button in self.window._banner.findChildren(QPushButton)]
                self.assertIn("Retry", labels)
                self.assertIn("Connection test", labels)
                self.window._on_renderer_stopped(self.window.browser, "Screen", 2, 11)
                self.assertIn("crashed", self.window._banner_text.text())
                self.assertIn("software_rendering", (folder / "settings.json").read_text(encoding="utf-8"))
                self.assertIn("page-problem", (folder / "laneora.log").read_text(encoding="utf-8"))

    def test_lightweight_mode_loads_a_tab_when_it_is_opened(self) -> None:
        from unittest.mock import patch

        from PyQt5.QtWidgets import QLabel

        session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": DAT_4})
        self.window.session = session
        self.window._services = [DAT_4]
        with patch("app.window.lightweight_enabled", return_value=True):
            self.window.open_service(DAT_4)
            lazy = [widget for widget in self.window.findChildren(QLabel) if widget.objectName() == "lazyTab"]
            self.assertEqual(len(lazy), 3)
            self.assertEqual(len(self.window.findChildren(QWebEngineView)), 1)
            self.assertEqual(
                self.window.findChildren(QWebEngineView)[0].page().profile().httpCacheMaximumSize(),
                8 * 1024 * 1024,
            )
            self.window.tabs.setCurrentIndex(2)
            self.assertEqual(len(self.window.findChildren(QWebEngineView)), 2)
            self.assertEqual(self.window.tabs.tabText(2), "Search 3")
            self.assertFalse(self.window.tabs.tabBar().isHidden())

    def test_connection_test_shows_a_pass_fail_summary(self) -> None:
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication, QLabel

        from app.connection_test import Check

        def runner(**kwargs):
            return [
                Check("one.dat.com", True, "HTTP 200, first byte 5 ms, sample 2 KB at 20 KB/s", "direct"),
                Check("proxy", True, "not configured; this PC connects directly", "info"),
            ]

        self.window._connection_runner = runner
        seen: list[str] = []

        def close_dialog() -> None:
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                return
            seen.extend(label.text() for label in dialog.findChildren(QLabel))
            dialog.accept()

        QTimer.singleShot(600, close_dialog)
        self.window.show_connection_test()
        self.assertTrue(any("PASS" in text and "one.dat.com" in text for text in seen))
        self.assertTrue(any("lightweight mode" in text for text in seen))


if __name__ == "__main__":
    unittest.main()
