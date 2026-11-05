"""Activate a specific Chrome window by title substring and screenshot it."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pyautogui
import pygetwindow as gw

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "dat_bloomington_box_search.png"


def main() -> int:
    needle = (sys.argv[1] if len(sys.argv) > 1 else "DAT One").lower()
    wins = [w for w in gw.getAllWindows() if w.title and needle in w.title.lower()]
    print("match", [(w.title, w.left, w.top, w.width, w.height) for w in wins])
    if not wins:
        return 1
    w = wins[0]
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
    except Exception as exc:  # noqa: BLE001
        print(exc)
    time.sleep(2)
    region = (max(0, w.left), max(0, w.top), max(50, w.width), max(50, w.height))
    pyautogui.screenshot(str(OUT), region=region)
    print("SAVED", OUT, w.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
