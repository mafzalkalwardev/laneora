"""Laneora main window: login → stream picker → proxied WebEngine tabs."""
from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any

import psutil
import requests
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFont, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView

from app import APP_NAME, PASSPHRASE, POWER_DAT, SERVER_URL, SPEEDTEST_URL, __version__
from app.auth import AuthError, AuthSession, authenticate, reauthenticate, start_logger_heartbeat
from app.browser import apply_cookies, attach_checker_script, clear_profile, inject_local_storage
from app.crypto_util import decrypt
from app.roster import load_roster, upsert_user
from app.streams import apply_http_proxy
from app.timezone_util import sync_timezone_from_ip


def resource_path(relative_path: str) -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for candidate in (
            os.path.join(meipass, relative_path),
            os.path.join(meipass, "app", "resources", relative_path),
            os.path.join(meipass, "resources", relative_path),
        ):
            if os.path.exists(candidate):
                return candidate
        return os.path.join(meipass, relative_path)
    return os.path.join(os.path.dirname(__file__), "resources", relative_path)


# Recovered IP Info encrypted payload (CryptoJS) from appv2.3 showSelectScreen
_IPINFO_BLOB = (
    "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"
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.session: AuthSession | None = None
        self._stop_logger = threading.Event()
        self.current_sub = ""
        self.success = 0
        self.store: list[dict[str, Any]] = []
        self.lst = "{}"
        self.sst = ""
        self.url = ""
        self.browser: QWebEngineView | None = None
        self.tabs: QTabWidget | None = None
        self.cookieStore = None

        icon_path = resource_path("app.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(980, 720)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(28, 28, 28, 28)
        self.layout.setSpacing(14)
        self._build_login()

    def _build_login(self) -> None:
        self.remove_all_widgets()
        self._roster = load_roster()

        logo_box = QHBoxLayout()
        logo_label = QLabel()
        mark = resource_path("mark.png")
        if os.path.exists(mark):
            pix = QPixmap(mark).scaledToWidth(96, Qt.SmoothTransformation)
            logo_label.setPixmap(pix)
        logo_box.addWidget(logo_label)
        logo_box.addStretch(1)
        self.layout.addLayout(logo_box)

        title = QLabel(APP_NAME)
        title.setObjectName("brandTitle")
        self.layout.addWidget(title)
        sub = QLabel(f"Auth + streams from {SERVER_URL}")
        sub.setObjectName("brandSubtitle")
        self.layout.addWidget(sub)

        roster_label = QLabel("Injected soft users:")
        roster_label.setObjectName("fieldLabel")
        self.layout.addWidget(roster_label)
        self.roster_combo = QComboBox()
        self.roster_combo.addItem("— type credentials manually —", None)
        for user in self._roster:
            display = user.get("label") or user["username"]
            self.roster_combo.addItem(display, user)
        self.roster_combo.currentIndexChanged.connect(self._on_roster_selected)
        self.layout.addWidget(self.roster_combo)

        user_label = QLabel("Username:")
        user_label.setObjectName("fieldLabel")
        self.layout.addWidget(user_label)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("soft.awwthat.com username")
        self.layout.addWidget(self.username_edit)

        pass_label = QLabel("Password:")
        pass_label.setObjectName("fieldLabel")
        self.layout.addWidget(pass_label)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("soft.awwthat.com password")
        self.layout.addWidget(self.password_edit)

        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.login)
        self.layout.addWidget(self.login_button)

        self.save_roster_button = QPushButton("Save current to roster")
        self.save_roster_button.setObjectName("secondaryButton")
        self.save_roster_button.clicked.connect(self._save_current_to_roster)
        self.layout.addWidget(self.save_roster_button)
        self.layout.addStretch(1)

        version_line = QLabel(
            f"{APP_NAME} v{__version__} · inject users: python scripts/add_user.py user pass"
        )
        version_line.setObjectName("brandSubtitle")
        self.layout.addWidget(version_line)

    def _on_roster_selected(self, _index: int) -> None:
        user = self.roster_combo.currentData()
        if not user:
            return
        self.username_edit.setText(user.get("username", ""))
        self.password_edit.setText(user.get("password", ""))

    def _save_current_to_roster(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        if not username or not password:
            QMessageBox.warning(self, "Error", "Enter username and password first.")
            return
        upsert_user(username, password)
        QMessageBox.information(self, "Saved", f"Added '{username}' to local roster.")
        # refresh dropdown without clearing typed fields
        current_user, current_pass = username, password
        self._build_login()
        self.username_edit.setText(current_user)
        self.password_edit.setText(current_pass)

    def kill_proc_tree(self, pid: int | None = None, including_parent: bool = True) -> None:
        pid = pid or os.getpid()
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.kill()
            if including_parent:
                parent.kill()
        except Exception as exc:  # noqa: BLE001
            print(exc)

    def stop_task(self) -> None:
        self._stop_logger.set()
        self.kill_proc_tree(including_parent=False)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_logger.set()
        event.accept()

    def login(self) -> None:
        try:
            session = authenticate(self.username_edit.text(), self.password_edit.text())
        except AuthError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Error", f"Login failed: {exc}")
            return

        self.session = session
        # Remember successful soft credentials for quicker retests
        try:
            upsert_user(session.username, self.password_edit.text().strip() or session.password)
        except Exception as exc:  # noqa: BLE001
            print("roster save:", exc)
        QMessageBox.information(
            self,
            "Success",
            "Login Successful - Connecting to High Speed Network Pool . . . . ",
        )
        self.setWindowTitle(
            f"{APP_NAME} v{__version__} — Connection line : {session.resp.get('p')} "
            f"- Stream : {session.resp.get('active_subs')}"
        )
        start_logger_heartbeat(session, self._on_multi_screen, self._stop_logger)
        self.show_select_screen(session)

    def _on_multi_screen(self) -> None:
        QMessageBox.warning(
            self,
            "Multiple Screens not allowed",
            "Allowed Users exceeded - exiting in 10 sec",
        )
        threading.Timer(10.0, lambda: (QApplication.quit(), self.stop_task())).start()

    def remove_all_widgets(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child = item.layout()
            if child is not None:
                while child.count():
                    nested = child.takeAt(0)
                    if nested.widget():
                        nested.widget().deleteLater()
        for toolbar in self.findChildren(QToolBar):
            self.removeToolBar(toolbar)
            toolbar.deleteLater()

    def show_select_screen(self, session: AuthSession) -> None:
        self.remove_all_widgets()
        resp = session.resp
        px, p, pu, pd = session.proxy_host, session.proxy_port, session.proxy_user, session.proxy_password

        ipinfo = QPushButton("IP Info")
        ipinfo.setObjectName("secondaryButton")
        ipinfo.clicked.connect(lambda: self.browse(_IPINFO_BLOB, px, p, pu, pd, "", 0))
        self.layout.addWidget(ipinfo)

        for opt in session.active_subs:
            btn = QPushButton(f"Load Stream: {opt}")
            btn.setObjectName("streamButton")
            # resp[opt] is encrypted payload for that stream
            btn.clicked.connect(
                lambda _checked=False, o=opt: self.browse(resp[o], px, p, pu, pd, o, 1)
            )
            self.layout.addWidget(btn, alignment=Qt.AlignBottom)

        self.showMaximized()

    def browse(self, br: str, px, p, pu, pd, opt: str, fc: int = 0) -> None:
        self.remove_all_widgets()
        self.current_sub = opt
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)

        px, pu, pd = str(px), str(pu), str(pd)
        p = int(p)
        apply_http_proxy(px, p, pu, pd)

        if fc == 1:
            threading.Thread(target=self._timezone_worker, daemon=True).start()

        full_make = json.loads(decrypt(PASSPHRASE, br))
        navtb = QToolBar("NavTb")
        try:
            linetext = requests.get(SERVER_URL + "/linetext", timeout=20)
            mylabel = QLabel(linetext.text)
        except Exception:  # noqa: BLE001
            mylabel = QLabel("")
        mylabel.setStyleSheet("QLabel { font-size: 18px; }")
        mylabel.setFont(QFont("Arial", 10))

        load_btn = QAction("Reconnect!", self)
        load_btn.setStatusTip("Search New Load")
        load_btn.triggered.connect(lambda: self.stream_again(opt))
        navtb.addAction(load_btn)

        reload_btn = QAction("Start Service", self)
        reload_btn.setStatusTip("Load new Tab")
        reload_btn.triggered.connect(lambda: self.new_tab(full_make, opt))
        navtb.addAction(reload_btn)

        speedtest_btn = QAction("SpeedTest", self)
        speedtest_btn.setStatusTip("Test Connection Speed")
        speedtest_btn.triggered.connect(self.speedtest)
        navtb.addAction(speedtest_btn)
        navtb.addWidget(mylabel)
        navtb.addSeparator()
        self.addToolBar(navtb)

        debug_info = QToolBar("Debug Info")
        debug_info.addWidget(
            QLabel(f"Support Info : Connection line : {p} - Stream : {opt}")
        )
        self.addToolBar(debug_info)

        self.make_tab(full_make, opt)

    def _timezone_worker(self) -> None:
        try:
            tz = sync_timezone_from_ip()
            print("System timezone changed successfully.", tz)
        except Exception as exc:  # noqa: BLE001
            print("TimeZone Error:", exc)

    def close_current_tab(self, i: int) -> None:
        if self.tabs is None:
            return
        self.tabs.removeTab(i)

    def new_tab(self, full_make: dict[str, Any], opt: str) -> None:
        self.make_tab(full_make, opt)

    def make_tab(self, full_make: dict[str, Any], opt: str) -> None:
        assert self.tabs is not None
        self.browser = QWebEngineView()
        attach_checker_script(self.browser)
        self.browser.loadProgress.connect(self.on_load_progress)
        self.browser.loadFinished.connect(self.on_load_finished)
        self.success = 0

        if "power" in (opt or "").lower():
            self.url = POWER_DAT
        else:
            self.url = str(full_make.get("url") or POWER_DAT)

        self.store = list(full_make.get("store") or [])
        self.lst = full_make.get("lst") or "{}"
        if not isinstance(self.lst, str):
            self.lst = json.dumps(self.lst)
        self.sst = str(full_make.get("sst") or "")

        profile = self.browser.page().profile()
        self.cookieStore = profile.cookieStore()
        self.cookieStore.deleteAllCookies()
        clear_profile(profile)
        apply_cookies(self.cookieStore, self.store)

        self.browser.load(QUrl(self.url))
        i = self.tabs.addTab(self.browser, "Screen")
        self.tabs.setCurrentIndex(i)

    def speedtest(self) -> None:
        if self.tabs is None:
            return
        view = QWebEngineView()
        view.page().profile().setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        view.load(QUrl(SPEEDTEST_URL))
        i = self.tabs.addTab(view, "SpeedTest")
        self.tabs.setCurrentIndex(i)

    def on_load_finished(self, ok: bool) -> None:
        if self.success:
            return
        if ok and self.browser is not None:
            self.success = 1
            inject_local_storage(self.browser, self.lst)
        elif self.browser is not None:
            self.browser.setUrl(QUrl(self.browser.url().toString()))

    def on_load_progress(self, progress: int) -> None:
        print(f"Page loading progress: {progress}%")

    def stream_again(self, opt: str) -> None:
        if not self.session:
            return
        try:
            session = reauthenticate(self.session)
            resp = session.resp
            self.browse(
                resp[opt],
                resp["px"],
                resp["p"],
                resp["pu"],
                resp["pd"],
                opt,
                0,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Error", f"Reconnect failed: {exc}")
