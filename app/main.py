"""Laneora application entrypoint."""
from __future__ import annotations

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.updater import check_for_updates, download_update


def _windows_app_id() -> None:
    """Separate the taskbar icon from python.exe and use the Laneora mark."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Laneora.DAT.Client")
    except Exception:
        pass


def _logo_icon(resource_path) -> QIcon:
    for name in ("mark.png", "logo.png", "app.ico"):
        path = resource_path(name)
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def load_stylesheet(app: QApplication, stylesheet_path: str) -> None:
    try:
        with open(stylesheet_path, "r", encoding="utf-8") as handle:
            app.setStyleSheet(handle.read())
    except OSError as exc:
        print("stylesheet:", exc)


def start() -> None:
    if "--self-check" in sys.argv or "--help" in sys.argv:
        if "--help" in sys.argv:
            message = (
                "Laneora\n"
                "  Laneora.exe                      start the app\n"
                "  Laneora.exe --lightweight        less memory, no GPU, after restart\n"
                "  Laneora.exe --software-rendering skip GPU compositing\n"
                "  Laneora.exe --self-check         exit 0 if this exe can start\n"
                "The server address comes from LANEORA_SERVER_URL. Laneora Soft.bat sets it.\n"
            )
            try:
                sys.stdout.write(message)
            except Exception:
                pass
        raise SystemExit(0)

    # Chromium reads GPU flags at startup, before the browser module is imported.
    from app.runtime_mode import apply_startup_flags

    apply_startup_flags()
    from app.window import MainWindow, resource_path

    # leftover updater cleanup: delete=<path>
    for arg in list(sys.argv):
        if "delete" in arg and "=" in arg:
            ds = arg.split("=", 1)
            if len(ds) > 1:
                try:
                    os.remove(ds[1])
                except OSError:
                    pass

    # High-DPI must be set before QApplication on some Qt builds.
    # App id must be set before any window, or Windows keeps the Python icon.
    _windows_app_id()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setWindowIcon(_logo_icon(resource_path))
    app.setApplicationName(
        f"{APP_NAME} - {__version__} - DAT board streams for dispatch teams"
    )
    load_stylesheet(app, resource_path("laneora.qss"))

    window = MainWindow()
    check_for_updates(window, on_start_download=lambda ver: download_update(window, ver))
    window.show()
    app.exec_()


if __name__ == "__main__":
    start()
