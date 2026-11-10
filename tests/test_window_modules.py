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
from app.services import DAT, DAT_3, DAT_6, DAT_DUAL


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
        self.assertEqual(_layout_buttons(self.window), ["Load DAT Stream"])

    def test_assigned_services_show_both_modules(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": "dat_dual,dat"})
        self.window.session = session
        self.window.show_select_screen(session)
        self.assertEqual(_layout_buttons(self.window), ["Load DAT Stream", "Dual DAT Search"])

    def test_picker_shows_only_the_modules_assigned_to_this_login(self) -> None:
        cases = {
            DAT_3: ["3 DAT Search"],
            DAT_6: ["6 DAT Search"],
            f"{DAT_6},{DAT_3}": ["3 DAT Search", "6 DAT Search"],
            f"{DAT},{DAT_DUAL},{DAT_3},{DAT_6}": [
                "Load DAT Stream",
                "Dual DAT Search",
                "3 DAT Search",
                "6 DAT Search",
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

    def test_three_and_six_open_separate_profiles(self) -> None:
        session = AuthSession(
            "ada",
            "secret",
            1,
            1,
            {**self.base, "services": f"{DAT},{DAT_DUAL},{DAT_3},{DAT_6}"},
        )
        self.window.session = session
        self.window._services = [DAT, DAT_DUAL, DAT_3, DAT_6]
        self.window.open_service(DAT_3)
        self.assertEqual(self.window._open_mode, DAT_3)
        self._assert_isolated_tabs(3, cache_capped=True)
        self.app.processEvents()
        self.window.open_service(DAT_6)
        self.assertEqual(self.window._open_mode, DAT_6)
        self._assert_isolated_tabs(6, cache_capped=True)
        labels = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertIn("3 Search", labels)
        self.assertIn("6 Search", labels)
        self.assertIn("Dual Search", labels)
        self.assertIn("DAT Search", labels)

    def test_original_module_still_hides_the_tab_bar(self) -> None:
        session = AuthSession("ada", "secret", 1, 1, {**self.base, "services": f"{DAT},{DAT_DUAL}"})
        self.window.session = session
        self.window._services = [DAT]
        self.window.browse(self.blob, "none", 0, "", "", "one", 0)
        self.assertEqual(self.window.tabs.count(), 1)
        self.assertTrue(self.window.tabs.tabBar().isHidden())
        self.assertEqual(self.window.tabs.tabText(0), "Screen")
        self.assertEqual(self.window.findChildren(QToolBar), [])

        self.window._services = [DAT, DAT_DUAL, DAT_3, DAT_6]
        self.window.browse(self.blob, "none", 0, "", "", "one", 0)
        self.assertEqual(self.window.tabs.count(), 1)
        self.assertTrue(self.window.tabs.tabBar().isHidden())
        self.assertEqual(self.window.tabs.tabText(0), "Screen")
        labels = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertIn("DAT Search", labels)
        self.assertIn("Dual Search", labels)
        self.assertIn("3 Search", labels)
        self.assertIn("6 Search", labels)

    def test_switching_modules_cancels_staggered_opens(self) -> None:
        from PyQt5.QtCore import QEventLoop, QTimer

        session = AuthSession(
            "ada",
            "secret",
            1,
            1,
            {**self.base, "services": f"{DAT},{DAT_6}"},
        )
        self.window.session = session
        self.window._services = [DAT, DAT_6]
        self.window.open_service(DAT_6)
        pending = list(self.window._search_timers)
        self.assertEqual(len(pending), 6)
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


if __name__ == "__main__":
    unittest.main()
