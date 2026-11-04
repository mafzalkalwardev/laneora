"""Laneora application entrypoint."""
from __future__ import annotations

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.updater import check_for_updates, download_update
from app.window import MainWindow, resource_path


def load_stylesheet(app: QApplication, stylesheet_path: str) -> None:
    try:
        with open(stylesheet_path, "r", encoding="utf-8") as handle:
            app.setStyleSheet(handle.read())
    except OSError as exc:
        print("stylesheet:", exc)


def start() -> None:
    # leftover updater cleanup: delete=<path>
    for arg in list(sys.argv):
        if "delete" in arg and "=" in arg:
            ds = arg.split("=", 1)
            if len(ds) > 1:
                try:
                    os.remove(ds[1])
                except OSError:
                    pass

    # High-DPI must be set before QApplication on some Qt builds
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
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
