"""Focus logged-in Chrome DAT tabs, wait for load, search Bloomington straight box, screenshot."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "dat_bloomington_box_search.png"
OUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyautogui", "pillow", "PyGetWindow", "-q"])
        import pyautogui
        import pygetwindow as gw

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.25

    # Prefer an already-open DAT window; also open search-loads
    subprocess.Popen(["cmd", "/c", "start", "", "https://one.dat.com/search-loads"], shell=False)
    time.sleep(6)

    def pick():
        wins = list(gw.getAllWindows())
        ranked = []
        for w in wins:
            t = (w.title or "")
            score = 0
            if "DAT One" in t:
                score += 5
            if "search" in t.lower():
                score += 2
            if "login.dat.com" in t:
                score += 3  # may need login
            if "Chrome" in t and w.width > 800:
                score += 1
            if score:
                ranked.append((score, w))
        ranked.sort(key=lambda x: -x[0])
        print("candidates:", [(s, w.title[:80]) for s, w in ranked[:8]])
        return ranked[0][1] if ranked else None

    target = pick()
    if not target:
        pyautogui.screenshot(str(OUT))
        print("no window; fullscreen saved")
        return 1

    try:
        if target.isMinimized:
            target.restore()
        target.activate()
    except Exception as exc:  # noqa: BLE001
        print("activate", exc)
    time.sleep(1)

    # Wait up to ~45s for DAT to leave loading state by polling screenshots brightness/title
    for i in range(15):
        title = target.title
        print(f"wait[{i}] title={title}")
        if "Loading" not in title and "DAT One" in title:
            # still may be loading in-page; give SPA time
            pass
        time.sleep(3)
        try:
            target.activate()
        except Exception:  # noqa: BLE001
            pass

    region = (max(0, target.left), max(0, target.top), max(100, target.width), max(100, target.height))
    # If login page is up, we cannot Soft-auth; grab evidence
    if "login.dat.com" in (target.title or ""):
        pyautogui.screenshot(str(OUT), region=region)
        print("LOGIN_PAGE", OUT)
        return 2

    # Click address bar check - ensure on search-loads
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyautogui.typewrite("https://one.dat.com/search-loads", interval=0.02)
    pyautogui.press("enter")
    time.sleep(10)

    # Origin field heuristic + Ctrl+F for equipment later
    x = region[0] + int(region[2] * 0.20)
    y = region[1] + int(region[3] * 0.28)
    pyautogui.click(x, y)
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite("Bloomington, CA", interval=0.05)
    time.sleep(1.5)
    pyautogui.press("down")
    pyautogui.press("enter")
    time.sleep(1)

    # Try filter button area
    for fx, fy in [(0.55, 0.28), (0.40, 0.22), (0.62, 0.22), (0.30, 0.35)]:
        pyautogui.click(region[0] + int(region[2] * fx), region[1] + int(region[3] * fy))
        time.sleep(0.4)

    # Type equipment via focused control
    pyautogui.typewrite("SB", interval=0.08)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1)
    pyautogui.press("enter")
    time.sleep(5)

    pyautogui.screenshot(str(OUT), region=region)
    print("SAVED", OUT, OUT.stat().st_size, "title=", target.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
