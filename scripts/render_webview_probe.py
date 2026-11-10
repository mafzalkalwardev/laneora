"""Offscreen check that a non-blank page paints. This is not one.dat.com."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5.QtCore import QTimer, QUrl
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.webview_flow import on_load_event  # noqa: E402

OUT = Path("/opt/cursor/artifacts/webview-local-render.png")
HTML = ROOT / "scripts" / "_render_probe.html"


def main() -> int:
    HTML.write_text(
        "<!doctype html><html><body style='margin:0;background:#c0392b'>"
        "<p style='color:#ffffff;font:24px sans-serif'>LANEORA-PIXEL</p>"
        "</body></html>",
        encoding="utf-8",
    )
    app = QApplication([])
    view = QWebEngineView()
    profile = QWebEngineProfile(view)
    view.setPage(QWebEnginePage(profile, view))
    view.resize(480, 320)
    seen: list[tuple[str, bool, str]] = []

    def finished(ok: bool) -> None:
        url = view.url().toString()
        action = on_load_event(url, bool(ok), False)
        seen.append((url, bool(ok), action))
        print(f"load_finished ok={int(bool(ok))} action={action} url={url}")
        if action == "ignore":
            return

        def inspected(text) -> None:
            print(f"document={text!r}")
            view.grab().save(str(OUT))
            image = view.grab().toImage()
            white = nonwhite = 0
            for y in range(0, image.height(), 4):
                for x in range(0, image.width(), 4):
                    color = QColor(image.pixel(x, y))
                    if color.red() > 250 and color.green() > 250 and color.blue() > 250:
                        white += 1
                    else:
                        nonwhite += 1
            print(f"grab white={white} nonwhite={nonwhite} saved={OUT}")
            if action == "inject" and text and "LANEORA-PIXEL" in str(text) and "192" in str(text):
                print("DOCUMENT_OK")
                app.exit(0)
                return
            print("DOCUMENT_FAIL")
            app.exit(1)

        view.page().runJavaScript(
            "document.body.innerText + ' ' + getComputedStyle(document.body).backgroundColor",
            inspected,
        )

    view.loadFinished.connect(finished)
    view.show()
    QTimer.singleShot(0, lambda: view.load(QUrl.fromLocalFile(str(HTML))))
    QTimer.singleShot(20000, lambda: app.exit(2))
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
