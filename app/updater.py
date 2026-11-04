"""Auto-update against soft.awwthat.com /latest_version + /update."""
from __future__ import annotations

import os
import sys
from typing import Callable

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from app import APP_NAME, SERVER_URL, __version__
from app.config import SKIP_UPDATE


class UpdateDownloadThread(QThread):
    download_complete = pyqtSignal(str)
    download_progress = pyqtSignal(int)

    def __init__(self, window, latest_version: str):
        super().__init__()
        self.win = window
        self.ls = latest_version

    def run(self) -> None:
        save_path = f"{APP_NAME} v{self.ls}.exe"
        try:
            head = requests.head(SERVER_URL + "/update", timeout=60)
            size = int(head.headers.get("Content-Length", 0))
            print(size)
            updated_version = requests.get(SERVER_URL + "/update", stream=True, timeout=300)
            downloaded = 0
            if updated_version.status_code == 200:
                with open(save_path, "wb") as handle:
                    for chunk in updated_version.iter_content(chunk_size=1024 * 64):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if size:
                            pct = int(min(100, downloaded * 100 / size))
                            self.download_progress.emit(pct)
                self.download_complete.emit(save_path)
            else:
                self.download_complete.emit("")
        except Exception as exc:  # noqa: BLE001
            print(exc)
            self.download_complete.emit("")


def execute_update(update_exe: str) -> None:
    current_file = os.path.abspath(sys.argv[0])
    arguments = [update_exe, f"delete={current_file}"]
    try:
        os.execl(update_exe, *arguments)
    except Exception as exc:  # noqa: BLE001
        print("Failed to execute update:", exc)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.strip().split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def check_for_updates(window, on_start_download: Callable[[str], None] | None = None) -> None:
    if SKIP_UPDATE:
        print("Update check skipped (local/test server mode)")
        return
    try:
        remote = requests.get(SERVER_URL + "/latest_version", timeout=20).text.strip()
        print("Remote Version :", remote)
        print("Local Version :", __version__)
        need = _version_tuple(remote) > _version_tuple(__version__)
        if not need:
            print("You have latest version")
            return
        QMessageBox.information(
            window,
            "Success",
            "New Version Available: please Update you App in your free time to avoid disruption in service.",
        )
        if on_start_download:
            on_start_download(remote)
        else:
            download_update(window, remote)
    except Exception as exc:  # noqa: BLE001
        print(exc)


def download_update(window, latest_version: str) -> None:
    thread = UpdateDownloadThread(window, latest_version)
    window._update_thread = thread  # keep ref

    def _done(path: str) -> None:
        if path:
            QMessageBox.information(window, "Downloaded", "Update downloaded successfully, now Executing")
            execute_update(path)
        else:
            QMessageBox.warning(window, "Error", "Latest version could not be downloaded")

    thread.download_complete.connect(_done)
    thread.start()
