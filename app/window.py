"""Laneora main window: login → stream picker → proxied WebEngine tabs."""
from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any

import psutil
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
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
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView

from app import APP_NAME, PASSPHRASE, SERVER_URL, SPEEDTEST_URL, __version__
from app.auth import AuthError, AuthSession, authenticate, reauthenticate, start_logger_heartbeat
from app.browser import apply_cookies, attach_checker_script, clear_profile, inject_local_storage
from app.client_log import client_log, log_path
from app.connection_test import format_report, run_checks
from app.crypto_util import decrypt
from app.roster import upsert_user
from app.runtime_mode import (
    arm_software_rendering,
    lightweight_cache_bytes,
    lightweight_enabled,
    save_settings,
    software_rendering_enabled,
)
from app.services import (
    DAT,
    DAT_DUAL,
    MULTI_SEARCH_TABS,
    search_open_delay_ms,
    search_tab_titles,
    search_url,
    service_by_id,
)
from app.session_sync import ProfileSessionSync
from app.streams import apply_http_proxy
from app.timezone_util import sync_timezone_from_ip


def _qt_object_deleted(obj: object) -> bool:
    """True once Qt has destroyed the C++ object behind this wrapper."""
    try:
        from PyQt5 import sip
    except ImportError:
        return False
    return sip.isdeleted(obj)


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
    "U2FsdGVkX182iQEVWXN2QjQMoLWf3GSDKUj5Hwq6/sbIEdAZegD1y+uXRo+Yd+j5RgjHsFYcCHw3aVn3+IC9zYP8V4hA7cveUYpMXOb7RVX8reMp0gGbR4w9dGB/ihSSqLS4SLiZnRs/UuRfIEMTBCgdPp1B867o0jKHuYKLWftftoj388r5+GzktAZ9F5wOZSIXds4YhkTtPtm9TgKm9Gknd5POIC8i2MWRsq7I764CdxD/KC7VIFMk7GVDfcNd/6NXTOVMsf/bo68KrBsVyiYBfuMl6oodjcXRTZxO1Xd6e2zC3UqXsvP0CXlQVQYefrwtf7RXGSKZ9RE4kPV1sweogqI2xCOIuIe3odLQH22xuo3wcKIyBF669Fux6ye9xS90fnCzRLsHM6arRE3ZQNEtpvIbrmeS6m1DBo1PeK0ZpsSmIDWN9mCpFnszr1qvUc2xqgSNzBtmgUQjIP7V6H7x8W/n7eS2zIDMFoFMQHaEya2n2eeyrKPvef9OOfTYmVU87BE4yKCubINzSt1Sowh2VPquTJ1AJmKvvD31jhvJktOY28nCEIzBfL9UXVMvDjfrfyvwZ1PbpV+VqTSt7lEck4hUzV1R2d96nmNxEHqgmnKS3VxGPDT1aqiIDJ/KgO5/ZhQ4xHx4KfMTWjzg4NEzIaP38O9gz2LplF5TbZagUgSQfQlEiGWzIa64kTRy/wadE1kTzfOKaicfHto2guec+Fzn2ZW+8JZ+XGKwi+ijnRCzgFsINTCuolHU8n457CmLkim7fn713uRZYrni7HZ038XBaRpWppUQKIqDUtcgj3izj+SyXqb7b8QaUaVv+yUCB9siMBOfF+KkpPZEMfPXSsYwOmeuok5Pmz4wO5ZvcScLW8tOb4gC3NpSjj0IxHPX8CMlg7ZcNwM3AIJRjfhjqhHSSvm2iOSmJZE4a7XnRidOIqNaz5LAmCGUTAaHZcPxLXdfEbsDcASXanQRhxlgwkNhBZjOAUP+IuasChvv22KNvOpEkUI+oFE80f8spmdFOGWEI98FDn/26KzIBiVKbieqjgrNas2CEUWNg2uJyM30vwDp1WhlTz/e2jFaYyyRMY6pbVwTeopLfI8S62uajAlgHPPxdu6Ms5ZhlZRfkcQQ9qa6lexqX2x2cUFM/lFeTMDmjk6CWmD1v+iejSXuwF/5FGTmAfgeNjWnbLyt3BovMClcPCTKkMceD4/n/07e9I8q9eH7mgp+L9SjqNGbSMhIj7cIVvcHVTU6IZMChAYFEX0ey+Cg6Ka2XooL7N5Rx2aXGL5rzlWiQvGOeNZFj8CKM4IirjbpUUrXhnwUhurSR2IKtKdNxPXDJGDZW6h5f1+2mf5kUK2aP+RZwa3XtF8rma0SDkSw9pyEljv+qDCYJ2UvF00znwApa7Hihiyaa6IweN7TnXvm0HQEXjQLVs5fGdv9nD4/fLwaibb6CPKsB0hlE5Ghyob6ospAG3H9cc5Xuxh/dODxHLTAFYlFU7Ix50TEBvIohtxzY6f0FB8C1zj5FV6YAQRAS0vk5ZpthQ4+LkAlkeltccwhNDYCXtLeiBDcy9MeXpFpfMnp6LpSJLVeZop+GZ6hC6rXSSpYVSesrfQGIadDjSpcdGVW/D8xROMjcXcPDxZ7lKxeiu1wBH1HjakBFQ2tQgGK+dBm4dKzojc/DX7riWJET97FbMFrAIkcQWzBFwGnPvkjq0LUl5ZMYYyRfen0RrN1EcSxWuVC3xMik0J6sDoyJ7VsZFhiOz/J6uqNau7yG/krCKIegSmu9x2B3fTuYfmErhOREsZRVsxXDwTPj8TIklTkiPTksICeDjdH7f0AXtXgLTzcYqnmUYVlJGVUX+TvbXJQ4Q3E9cBJmtDBffkvbsZqnmULZXrjaqTNTk6eYoFcupWhTNKpoCkkzY9fvTBkEp6/1xoAPxMXfkcdX8250iGupSHhE3n1KxDhL2OI3ExU5f1g3WharWWQkRV8LSLoHsQJd6jdWYCrWoeoOy1CFFQ+VVmzKoENx4683+RoHraNr5hdBfUKdk5plZtGoO1d1dDXGf4394VvK4INqtznxSJZOfmkw7LxCe16y9vFIH+ErswLHk9nzIy/oQSL0jq4N4pJ2C+y9AxNtbW/xNfvUNh1efhTDGCJdmQLAQW4yJ6CLQB5E4/31uJobDKucOb5T1O2V6E1x/bWrUGaaoWDTqeQ/fqASY26krpufokRirJS2qYtkybecBn9OtV5mPdrw5A2XTaztrWYS0jwZQ5HZpQ/oGT1iNcCuPvkVKjQ9jtz4yYOQREw07LiTTkB0mm5LT0sTeLmp7Wo1/ZDCI6z3ZXqojAN/HRh7/2z2oEIA+fZ5TRzJbep3OOt/bMCA/S/FyUDAmZ2WT+8rP7GUIxYcTLPrFiQNKWm8eg2Q1Tvu97sfqe3E8J9Y+tDKo+QeTlFu0EbwjpxhPlcAcSVFnEmxkGPh0hnjunpsCVnSAmODlXdoGk8N8E7R8gWc3eFYhOcR9v3AYufKStqwvNluIV6tZvj19iyFjs4SDVQGRWbaIL8h39Zgz/Vm9JZLR98du6aH5WLrHbRSJU0glze8KoyB2OJtn19HjqiQmdI4iW97muMz14rQg9A9Bg0FtoV5yRpMauqUDwOtlFJ/GYA805AHq83d4CPMtaARegD4Yvkdf3fdZd+d5HflDOvqme/VS7IQbZ+pUwZL7qvGX7+GDOswqG+Y1UFxIqH8AzsZwMI9yeS+WjNEoS3e426W64NYyvjWCON5tqtSSgcdWyv/5kTXqxjMCZGUFLEy/ZZXjcAz40Ms4NQnTD6pPaYje0tPprfSApZSREztuEDWEuZRfGHEDojqE6cgHme1yxDek7dE2vZVL3giCixAAbPJ6Awo/BDgK4h5ei9OHvUB5qZObC3EqGLoYcZzOzKeBU3ZA7gLr3mg4YyP1DiHB/iX5oj0kQfRoYjqN3KCLILtyeVCechrSIEF44pGbK2kGCfsYv+Ajzv5E9Zyu9kX4/Q3WLfAQUb/K4mGqf1y2OYZEHrcbqBVW94Zd/LPMc0ztr7uOJTOZheOFL4Gg9bik8XzylLDhsPP5B+R4mloF/SvtYn/PZWxBTkbZhFFjsyzIWt8wXqPgdoGlNh1+4K0COum3l325lxgtLJdkicOQLRzTyNcHsGPRW90wAB1L7QVkLMldw54+uYHfsbWD3fmgVdw7JIjQpMmcby+B505M5DNQFrlb4rpVstROu2RjU1m1lh/VRcdninhTvYpxtebynpzCMWMzIKXCgoLRpw8I7CBEtnx868TaKgFaFloI/qjx4Kkg17/Q8rHCJWwP9py2KbKQn8xuazSbrLNR68jQoCbm7hOls00rteSq5K6+WMiNGll9cPqQZRJ6NYqw+ZuY8LkGkD/yJUR4/5+IufBI5KQLNIvxFpdjEcitxArTrUWXxT6tMtxaJuEnVu30w5BS9sRE66s8a8mOKzBZ8UvDdASO0iwYs6REGB8w+iI/7j+Id9ca39c0hAhJy60lGlsgDJhPcDrGhdMHGLACsXsORbQS94rkZ3IweLZideoX1YmLHGm58femXTazE3sE4mAgmZh8/nj61EmG6QEKmEO60cgHjUGFKYcl0LvXPTNp8Uf7uJFpaGd+pu58MT5ld4hMbHoEt6lWsQJFWREB2leykf03e6t8QLN0PachqbH/HdHtGN2HiwUzsW5+Fkmq+nqyHxjZgKPGDyKCcInA12uP+MKs0I38LYqU+2n5oe8GDcU9yj8CKZVp8+bTtRNRxHflLbsZZ9K/lmCixMS6EcnbgMuKQbhA9gOnAy+g/D5+HH2vmpHG2fR/sYv++h0RcSVMEpXTzNcTcs6dUToDvH4++dlHpCeZBIU+H1/XtxAYewhgDC0GH/BY/Xrd3Lkix15nYIhNYVM5sexvVE+UgcH74Pnnx8V8433buN9wvSbfnkWHRMKq1sn5OUDID7m6iqUFTgmOISbnkL63Np7XUhzNE1ODr75wgaE95wRiDXIQiW5Od4DcALPSzgxMVjr40CjFI4Vva4W6/t"
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
        # Services assigned at login. Default matches accounts that have no list yet.
        self._services: list[str] = [DAT]
        self._open_mode = DAT
        self._view_states: list[dict[str, Any]] = []
        self._search_timers: list[QTimer] = []
        self._search_generation = 0
        self._session_sync: ProfileSessionSync | None = None
        self._banner: QFrame | None = None
        self._banner_text: QLabel | None = None
        self._load_failures: dict[int, int] = {}
        self._load_timers: dict[int, QTimer] = {}
        self._load_timeout_ms = 20_000
        self._loaded_ids: set[int] = set()
        self._pending_tabs: dict[int, dict[str, Any]] = {}
        self._started_lightweight = lightweight_enabled()
        self._connection_runner = run_checks

        for name in ("mark.png", "logo.png", "app.ico"):
            icon_path = resource_path(name)
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    break
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
        self.layout.addStretch(1)

        card = QWidget()
        card.setObjectName("loginCard")
        card.setFixedWidth(420)
        form = QVBoxLayout(card)
        form.setContentsMargins(36, 32, 36, 32)
        form.setSpacing(10)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        mark = resource_path("mark.png")
        if os.path.exists(mark):
            pix = QPixmap(mark).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pix)
        form.addWidget(logo_label)

        title = QLabel(APP_NAME)
        title.setObjectName("brandTitle")
        title.setAlignment(Qt.AlignCenter)
        form.addWidget(title)
        form.addSpacing(14)

        user_label = QLabel("Username")
        user_label.setObjectName("fieldLabel")
        form.addWidget(user_label)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")
        form.addWidget(self.username_edit)
        form.addSpacing(6)

        pass_label = QLabel("Password")
        pass_label.setObjectName("fieldLabel")
        form.addWidget(pass_label)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Password")
        form.addWidget(self.password_edit)
        self.username_edit.returnPressed.connect(self.password_edit.setFocus)
        self.password_edit.returnPressed.connect(self.login)
        form.addSpacing(12)

        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.clicked.connect(self.login)
        form.addWidget(self.login_button)
        self._add_support_controls(form)

        self.layout.addWidget(card, alignment=Qt.AlignHCenter)
        self.layout.addStretch(1)

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
        self._services = list(session.services)
        # Remember successful soft credentials for quicker retests
        try:
            upsert_user(session.username, self.password_edit.text().strip() or session.password)
        except Exception as exc:  # noqa: BLE001
            print("roster save:", exc)
        QMessageBox.information(self, "Success", "Login Successful")
        if self._services == [DAT]:
            self.setWindowTitle(f"{APP_NAME} v{__version__} — DAT One")
        else:
            self.setWindowTitle(f"{APP_NAME} v{__version__}")
        start_logger_heartbeat(session, self._on_multi_screen, self._stop_logger)
        self.show_select_screen(session)

    def _on_multi_screen(self) -> None:
        QMessageBox.warning(
            self,
            "Multiple Screens not allowed",
            "Allowed Users exceeded - exiting in 10 sec",
        )
        threading.Timer(10.0, lambda: (QApplication.quit(), self.stop_task())).start()

    def _cancel_pending_searches(self) -> None:
        """Drop search opens that have not run yet.

        3-search and 4-search stagger later tabs by up to about a second and a
        half. Switching modules deletes those views immediately after, and a
        leftover timer would apply cookies to a view Qt has already destroyed.
        """
        for timer in self._search_timers:
            timer.stop()
            timer.deleteLater()
        self._search_timers = []
        self._search_generation += 1
        self._load_failures.clear()
        for timer in self._load_timers.values():
            timer.stop()
            timer.deleteLater()
        self._load_timers = {}
        self._loaded_ids.clear()
        self._pending_tabs = {}
        self._banner = None
        self._banner_text = None
        if self._session_sync is not None:
            self._session_sync.close()
            self._session_sync = None

    def _schedule_search_open(self, delay_ms: int, callback) -> None:
        generation = self._search_generation
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _run(generation: int = generation, callback=callback) -> None:
            if generation != self._search_generation:
                return
            callback()

        timer.timeout.connect(_run)
        timer.start(delay_ms)
        self._search_timers.append(timer)

    def remove_all_widgets(self) -> None:
        self._cancel_pending_searches()
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

    def _add_support_controls(self, layout: QVBoxLayout) -> None:
        button = QPushButton("Connection test")
        button.setObjectName("secondaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.show_connection_test)
        layout.addWidget(button)
        box = QCheckBox("Lightweight mode")
        box.setToolTip("Loads extra search tabs when you open them, and skips GPU rendering after a restart.")
        box.blockSignals(True)
        box.setChecked(self._started_lightweight)
        box.blockSignals(False)
        box.toggled.connect(self._toggle_lightweight)
        layout.addWidget(box)

    def _toggle_lightweight(self, checked: bool) -> None:
        checked = bool(checked)
        if checked:
            save_settings(lightweight=True, software_rendering=True)
        else:
            save_settings(lightweight=False)
        if checked == self._started_lightweight:
            return
        QMessageBox.information(
            self,
            "Restart Laneora",
            "Lightweight mode is saved. Close Laneora and open it again.\n"
            "You can also start it with --lightweight, or --software-rendering for graphics only.",
        )

    def _proxy_host(self) -> str:
        if self.session is None:
            return ""
        host = str(self.session.proxy_host or "").strip()
        if host.lower() in ("", "none", "direct", "local", "0", "false"):
            return ""
        return host

    def _watch_view(self, view: QWebEngineView, title: str) -> None:
        page = view.page()
        if hasattr(page, "renderProcessTerminated"):
            page.renderProcessTerminated.connect(
                lambda status, code, view=view, title=title: self._on_renderer_stopped(view, title, status, code)
            )
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda view=view, title=title: self._on_load_timeout(view, title))
        timer.start(self._load_timeout_ms)
        self._load_timers[id(view)] = timer

    def _note_load_result(self, view: QWebEngineView | None, ok: bool, title: str) -> None:
        if view is None or _qt_object_deleted(view):
            return
        if ok:
            self._loaded_ids.add(id(view))
            timer = self._load_timers.get(id(view))
            if timer is not None:
                timer.stop()
            return
        url = ""
        try:
            url = view.url().toString()
        except RuntimeError:
            url = ""
        count = self._load_failures.get(id(view), 0) + 1
        self._load_failures[id(view)] = count
        client_log("load-failed", tab=title, attempt=count, url=url, proxy=self._proxy_host() or "none")
        if url and url != "about:blank" and count < 2:
            view.setUrl(QUrl(url))
            return
        if not url or url == "about:blank":
            reason = "The browser stayed on a blank page"
        else:
            reason = "The page did not load"
        self._show_problem(title, reason)

    def _on_load_timeout(self, view: QWebEngineView, title: str) -> None:
        if _qt_object_deleted(view) or id(view) in self._loaded_ids:
            return
        self._show_problem(title, "The page did not finish loading within 20 seconds")

    def _on_renderer_stopped(self, view: QWebEngineView, title: str, status: object, code: object) -> None:
        if _qt_object_deleted(view):
            return
        try:
            status_value = int(status)
        except (TypeError, ValueError):
            status_value = -1
        words = {
            0: "exited normally",
            1: "exited abnormally",
            2: "crashed",
            3: "was killed",
        }.get(status_value, "stopped")
        self._show_problem(
            title,
            f"The browser renderer {words} (code {code}). A white page is what that looks like",
            arm_software=status_value in (1, 2, 3),
        )

    def _show_problem(self, title: str, reason: str, *, arm_software: bool = False) -> None:
        from app.client_log import redact_text

        safe_reason = redact_text(reason)
        client_log("page-problem", tab=title, reason=safe_reason, proxy=self._proxy_host() or "none")
        extra = ""
        if arm_software and not self._started_lightweight and not software_rendering_enabled():
            arm_software_rendering(safe_reason)
            extra = " The next start will skip GPU rendering."
        elif arm_software and software_rendering_enabled():
            extra = " Software rendering is already on. Send the log file."
        proxy = self._proxy_host()
        proxy_line = f" Traffic uses proxy {proxy}." if proxy else " No proxy is set."
        message = (
            f"{title}: {safe_reason}.{proxy_line}{extra}\n"
            f"Log file: {log_path()}\n"
            "The log has no passwords or cookies."
        )
        self._ensure_banner()
        if self._banner_text is not None:
            self._banner_text.setText(message)
        if self._banner is not None:
            self._banner.show()

    def _ensure_banner(self) -> None:
        if self._banner is not None:
            return
        banner = QFrame()
        banner.setObjectName("errorBanner")
        layout = QVBoxLayout(banner)
        text = QLabel()
        text.setObjectName("errorText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(text)
        row = QHBoxLayout()
        retry = QPushButton("Retry")
        retry.setObjectName("retryButton")
        retry.clicked.connect(self._retry_current)
        test = QPushButton("Connection test")
        test.setObjectName("secondaryButton")
        test.clicked.connect(self.show_connection_test)
        light = QPushButton("Use lightweight mode")
        light.setObjectName("secondaryButton")
        light.clicked.connect(lambda: self._toggle_lightweight(True))
        for button in (retry, test, light):
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button)
        layout.addLayout(row)
        self.layout.insertWidget(0, banner)
        self._banner = banner
        self._banner_text = text

    def _retry_current(self) -> None:
        if self._banner is not None:
            self._banner.hide()
        session = self.session
        if session is None:
            return
        blob = session.resp.get("one")
        if not blob:
            return
        proxy = (
            session.proxy_host,
            session.proxy_port,
            session.proxy_user,
            session.proxy_password,
        )
        if self._open_mode in MULTI_SEARCH_TABS:
            self.browse_multi(self._open_mode, blob, *proxy, 0)
            return
        self.browse(blob, *proxy, "one", 0)

    def show_connection_test(self) -> None:
        from PyQt5.QtCore import QObject, pyqtSignal

        class _Bridge(QObject):
            done = pyqtSignal(str)

        dialog = QDialog(self)
        dialog.setWindowTitle("Connection test")
        dialog.resize(680, 460)
        layout = QVBoxLayout(dialog)
        text = QLabel("Checking DAT and the proxy…")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(text)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        host = port = user = password = ""
        port = 0
        if self.session is not None:
            host = self.session.proxy_host
            port = self.session.proxy_port
            user = self.session.proxy_user
            password = self.session.proxy_password
        bridge = _Bridge(dialog)

        def apply_result(body: str) -> None:
            from app.client_log import redact_text

            safe = redact_text(body)
            text.setText(safe + f"\n\nLog file: {log_path()}")

        bridge.done.connect(apply_result)

        def work() -> None:
            try:
                checks = self._connection_runner(
                    proxy_host=host,
                    proxy_port=port,
                    proxy_user=user,
                    proxy_password=password,
                )
                body = format_report(checks)
            except Exception as exc:  # noqa: BLE001
                body = f"The connection test could not finish ({type(exc).__name__})."
            client_log("connection-test", summary=body.split("\n")[-1][:240])
            bridge.done.emit(body)

        threading.Thread(target=work, daemon=True).start()
        dialog.exec_()

    def show_select_screen(self, session: AuthSession) -> None:
        self._services = list(session.services)
        # Original module only: keep the single "Load DAT Stream" screen.
        if self._services == [DAT]:
            self._show_original_dat_picker(session)
            return
        self._show_service_picker(session)

    def _show_original_dat_picker(self, session: AuthSession) -> None:
        self.remove_all_widgets()
        resp = session.resp
        px, p, pu, pd = session.proxy_host, session.proxy_port, session.proxy_user, session.proxy_password
        blob = resp.get("one")
        if not blob:
            QMessageBox.warning(self, "Error", "DAT One stream is not on this account.")
            self._build_login()
            return

        self.layout.addStretch(1)
        btn = QPushButton("Load DAT Stream")
        btn.setObjectName("streamButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(
            lambda _checked=False: self.browse(blob, px, p, pu, pd, "one", 1)
        )
        holder = QWidget()
        holder.setFixedWidth(420)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(btn)
        self._add_support_controls(holder_layout)
        self.layout.addWidget(holder, alignment=Qt.AlignHCenter)
        self.layout.addStretch(1)
        self.showMaximized()

    def _show_service_picker(self, session: AuthSession) -> None:
        self.remove_all_widgets()
        if not session.resp.get("one"):
            QMessageBox.warning(self, "Error", "DAT One stream is not on this account.")
            self._build_login()
            return

        self.layout.addStretch(1)
        holder = QWidget()
        holder.setFixedWidth(420)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(14)
        for service_id in self._services:
            spec = service_by_id(service_id)
            btn = QPushButton(spec["button"])
            btn.setObjectName("streamButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, sid=service_id: self.open_service(sid))
            holder_layout.addWidget(btn)
            hint = QLabel(spec["description"])
            hint.setObjectName("brandSubtitle")
            hint.setAlignment(Qt.AlignCenter)
            hint.setWordWrap(True)
            holder_layout.addWidget(hint)
        self._add_support_controls(holder_layout)
        self.layout.addWidget(holder, alignment=Qt.AlignHCenter)
        self.layout.addStretch(1)
        self.showMaximized()

    def open_service(self, service_id: str) -> None:
        session = self.session
        if session is None:
            return
        blob = session.resp.get("one")
        if not blob:
            QMessageBox.warning(self, "Error", "DAT One stream is not on this account.")
            return
        proxy = (
            session.proxy_host,
            session.proxy_port,
            session.proxy_user,
            session.proxy_password,
        )
        if service_id in MULTI_SEARCH_TABS:
            self.browse_multi(service_id, blob, *proxy, 1)
            return
        self.browse(blob, *proxy, "one", 1)

    def browse(self, br: str, px, p, pu, pd, opt: str, fc: int = 0) -> None:
        self.remove_all_widgets()
        self.current_sub = opt
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()

        px, pu, pd = str(px), str(pu), str(pd)
        p = int(p)
        apply_http_proxy(px, p, pu, pd)

        if fc == 1:
            threading.Thread(target=self._timezone_worker, daemon=True).start()

        full_make = json.loads(decrypt(PASSPHRASE, br))
        self.make_tab(full_make, opt)
        self._open_mode = DAT
        self.setWindowTitle(f"{APP_NAME} v{__version__} — DAT One")
        self._add_module_bar(DAT)

    def browse_dual(self, br: str, px, p, pu, pd, fc: int = 0) -> None:
        """Two DAT search tabs. Each tab is a separate WebEngine profile."""
        self.browse_multi(DAT_DUAL, br, px, p, pu, pd, fc)

    def browse_multi(self, service_id: str, br: str, px, p, pu, pd, fc: int = 0) -> None:
        """Open one multi-search module. Each tab is a separate WebEngine profile."""
        count = MULTI_SEARCH_TABS[service_id]
        spec = service_by_id(service_id)
        self.remove_all_widgets()
        self._open_mode = service_id
        self.current_sub = "one"
        self._view_states = []
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.tabBar().show()
        self.layout.addWidget(self.tabs)

        px, pu, pd = str(px), str(pu), str(pd)
        p = int(p)
        apply_http_proxy(px, p, pu, pd)
        if fc == 1:
            threading.Thread(target=self._timezone_worker, daemon=True).start()

        full_make = json.loads(decrypt(PASSPHRASE, br))
        # Dual search keeps the original uncapped cache. Larger modules cap it.
        # Lightweight mode caps every profile and creates later tabs on demand.
        light = lightweight_enabled()
        cap_cache = light or count > MULTI_SEARCH_TABS[DAT_DUAL]
        self._session_sync = ProfileSessionSync()
        for index, title in enumerate(search_tab_titles(count)):
            if light and index > 0:
                placeholder = QLabel("This search loads when you open the tab.")
                placeholder.setObjectName("lazyTab")
                placeholder.setAlignment(Qt.AlignCenter)
                placeholder.setWordWrap(True)
                self.tabs.addTab(placeholder, title)
                self._pending_tabs[index] = {
                    "full_make": full_make,
                    "title": title,
                    "open_delay_ms": 0,
                    "cap_cache": cap_cache,
                }
                continue
            self._mount_independent_search(
                full_make,
                title,
                open_delay_ms=search_open_delay_ms(index, count),
                cap_cache=cap_cache,
            )
        if self._pending_tabs:
            self.tabs.currentChanged.connect(self._open_pending_tab)
        self._session_sync.start()
        self.tabs.setCurrentIndex(0)
        current = self.tabs.currentWidget()
        if isinstance(current, QWebEngineView):
            self.browser = current
        self.setWindowTitle(f"{APP_NAME} v{__version__} — {spec['label']}")
        self._add_module_bar(service_id)
        self.showMaximized()

    def _open_pending_tab(self, index: int) -> None:
        spec = self._pending_tabs.pop(index, None)
        if spec is None or self.tabs is None:
            return
        title = str(spec["title"])
        self.tabs.blockSignals(True)
        self.tabs.removeTab(index)
        self._mount_independent_search(
            spec["full_make"],
            title,
            open_delay_ms=int(spec["open_delay_ms"]),
            cap_cache=bool(spec["cap_cache"]),
            tab_index=index,
        )
        self.tabs.blockSignals(False)
        self.tabs.setCurrentIndex(index)

    def _add_module_bar(self, current: str) -> None:
        """Let a login that has several services switch. One service keeps the old chrome."""
        if len(self._services) < 2:
            return
        bar = QToolBar("Services")
        bar.setMovable(False)
        for service_id in self._services:
            spec = service_by_id(service_id)
            button = QPushButton(spec["short"])
            button.setCursor(Qt.PointingHandCursor)
            if service_id != current:
                button.setObjectName("secondaryButton")
            button.clicked.connect(lambda _checked=False, sid=service_id: self.open_service(sid))
            bar.addWidget(button)
        self.addToolBar(bar)

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
        self._watch_view(self.browser, "Screen")
        self.browser.loadProgress.connect(self.on_load_progress)
        self.browser.loadFinished.connect(self.on_load_finished)
        self.success = 0

        # DAT One opens Search Loads only. Other side tabs stay hidden via the checker.
        self.url = search_url(full_make, opt)

        self.store = list(full_make.get("store") or [])
        self.lst = full_make.get("lst") or "{}"
        if not isinstance(self.lst, str):
            self.lst = json.dumps(self.lst)
        self.sst = str(full_make.get("sst") or "")

        profile = self.browser.page().profile()
        if lightweight_enabled():
            profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            profile.setHttpCacheMaximumSize(lightweight_cache_bytes())
        self.cookieStore = profile.cookieStore()
        # deleteAllCookies is async. Setting cookies in the same turn gets wiped
        # and DAT stays on a blank page. Apply the session after the delete runs.
        self.cookieStore.deleteAllCookies()
        clear_profile(profile)
        url = self.url
        store = list(self.store)
        cookie_store = self.cookieStore

        def _open_stream() -> None:
            if self.browser is None:
                return
            apply_cookies(cookie_store, store)
            self.browser.load(QUrl(url))

        self._schedule_search_open(400, _open_stream)
        i = self.tabs.addTab(self.browser, "Screen")
        self.tabs.setCurrentIndex(i)

    def _mount_independent_search(
        self,
        full_make: dict[str, Any],
        title: str,
        *,
        open_delay_ms: int = 400,
        cap_cache: bool = False,
        tab_index: int | None = None,
    ) -> None:
        """One DAT search tab with its own profile.

        The captured session and the app proxy are the same ones the single
        search uses. Navigation stays on this profile. Login cookies and auth
        tokens are copied to the module's other tabs when they change.
        """
        assert self.tabs is not None
        view = QWebEngineView()
        profile = QWebEngineProfile(view)
        if lightweight_enabled():
            profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            profile.setHttpCacheMaximumSize(lightweight_cache_bytes())
        elif cap_cache:
            profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
            profile.setHttpCacheMaximumSize(32 * 1024 * 1024)
        page = QWebEnginePage(profile, view)
        view.setPage(page)
        attach_checker_script(view)
        self._watch_view(view, title)

        url = search_url(full_make, "one")
        store = list(full_make.get("store") or [])
        lst = full_make.get("lst") or "{}"
        if not isinstance(lst, str):
            lst = json.dumps(lst)

        cookie_store = profile.cookieStore()
        if self._session_sync is not None:
            self._session_sync.watch(profile, view)
        # deleteAllCookies is async. Setting cookies in the same turn gets wiped.
        cookie_store.deleteAllCookies()
        clear_profile(profile)
        state: dict[str, Any] = {"success": 0}
        self._view_states.append(state)

        def on_finished(ok: bool, view: QWebEngineView = view, lst: str = lst, state: dict[str, Any] = state, title: str = title) -> None:
            self._note_load_result(view, ok, title)
            if not ok or state["success"]:
                return
            state["success"] = 1
            inject_local_storage(view, lst)

        view.loadFinished.connect(on_finished)
        view.loadProgress.connect(self.on_load_progress)

        def _open(
            view: QWebEngineView = view,
            cookie_store=cookie_store,
            store: list[dict[str, Any]] = store,
            url: str = url,
            profile: QWebEngineProfile = profile,
        ) -> None:
            if _qt_object_deleted(view):
                return
            cookies = store
            if self._session_sync is not None:
                cookies = self._session_sync.overlay_cookies(store)
            apply_cookies(cookie_store, cookies)
            if self._session_sync is not None:
                self._session_sync.note_opened(profile)
            view.load(QUrl(url))

        self._schedule_search_open(open_delay_ms, _open)
        if tab_index is None:
            self.tabs.addTab(view, title)
        else:
            self.tabs.insertTab(tab_index, view, title)

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
        self._note_load_result(self.browser, ok, "Screen")
        if not ok or self.success or self.browser is None:
            return
        self.success = 1
        inject_local_storage(self.browser, self.lst)

    def on_load_progress(self, progress: int) -> None:
        print(f"Page loading progress: {progress}%")

    def stream_again(self, opt: str) -> None:
        if not self.session:
            return
        try:
            session = reauthenticate(self.session)
            resp = session.resp
            if self._open_mode in MULTI_SEARCH_TABS:
                self.browse_multi(self._open_mode, resp["one"], resp["px"], resp["p"], resp["pu"], resp["pd"], 0)
                return
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
