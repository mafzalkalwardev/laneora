"""
Drive the specific Chrome window (DAT login + Urban VPN / Person 1),
not the user's other Chrome profiles. Soft credentials from data/users.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pyautogui
import pygetwindow as gw
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "dat_bloomington_box_search.png"
OUT.parent.mkdir(parents=True, exist_ok=True)
SOFT = "https://soft.awwthat.com"


def soft_auth(username: str, password: str) -> dict:
    r = requests.get(
        SOFT + "/authenticate",
        params={"username": username, "key": password, "value": "1", "is_alive": "1"},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    return {"http": r.status_code, "body": r.text[:500], "json": None if r.status_code != 200 else _safe_json(r)}


def _safe_json(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def pick_target_chrome():
    """Prefer the DAT login / Urban-VPN chrome from the agent screenshot, not GitHub/Claude tabs."""
    ranked = []
    for w in gw.getAllWindows():
        t = w.title or ""
        if not t or w.width < 600:
            continue
        score = 0
        if "login.dat.com" in t:
            score += 10
        if "DAT One" in t or "DAT Freight" in t:
            score += 8
        if "Attention Required" in t or "Cloudflare" in t:
            score += 4
        if "Urban VPN" in t:
            score += 6
        if "0.0.0.53" in t:
            score += 5
        # deprioritize user's normal work tabs
        if any(x in t for x in ("GitHub", "Claude", "Gmail", "Upwork", "Messages", "Laneora repo")):
            score -= 20
        if "Chrome" in t and score > 0:
            ranked.append((score, w))
    ranked.sort(key=lambda x: -x[0])
    print("ranked:", [(s, w.title[:90]) for s, w in ranked[:10]])
    return ranked[0][1] if ranked else None


def main() -> int:
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3

    roster = json.loads((ROOT / "data" / "users.json").read_text(encoding="utf-8"))
    users = roster.get("users") or []
    print("Soft roster users:", [u.get("username") for u in users])
    soft_results = {}
    ok_session = None
    for u in users:
        res = soft_auth(str(u["username"]), str(u["password"]))
        soft_results[u["username"]] = {"http": res["http"], "preview": res["body"][:120]}
        print("SOFT", u["username"], soft_results[u["username"]])
        if res["http"] == 200 and isinstance(res.get("json"), dict) and res["json"].get("status") == "okie":
            ok_session = (u, res["json"])
            break

    target = pick_target_chrome()
    if not target:
        print("Target chrome not found")
        return 1
    try:
        if target.isMinimized:
            target.restore()
        target.activate()
    except Exception as exc:  # noqa: BLE001
        print("activate", exc)
    time.sleep(1.5)

    # Close Chrome profile flyout if open (Esc)
    pyautogui.press("esc")
    time.sleep(0.4)

    region = (max(0, target.left), max(0, target.top), max(50, target.width), max(50, target.height))
    pyautogui.screenshot(str(OUT.with_name("dat_target_before.png")), region=region)

    if not ok_session:
        # Soft still broken — cannot inject Soft DAT cookies. Stay on this chrome and document.
        pyautogui.screenshot(str(OUT), region=region)
        print("SOFT_AUTH_FAILED; saved login chrome screenshot", OUT)
        (ROOT / "artifacts" / "soft_auth_status.json").write_text(
            json.dumps(soft_results, indent=2), encoding="utf-8"
        )
        return 2

    user, payload = ok_session
    print("Soft ok for", user["username"], "subs", payload.get("active_subs"))

    # Soft-authenticated path: open DAT One search (cookies would normally come from Soft store;
    # in this browser we can only navigate — full cookie inject needs Laneora WebEngine).
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyautogui.typewrite("https://one.dat.com/search-loads", interval=0.02)
    pyautogui.press("enter")
    time.sleep(12)

    # Search Bloomington CA / straight box
    x = region[0] + int(region[2] * 0.22)
    y = region[1] + int(region[3] * 0.28)
    pyautogui.click(x, y)
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite("Bloomington, CA", interval=0.05)
    time.sleep(1)
    pyautogui.press("enter")
    time.sleep(2)
    pyautogui.typewrite("Straight Box", interval=0.05)
    pyautogui.press("enter")
    time.sleep(5)
    pyautogui.screenshot(str(OUT), region=region)
    print("SAVED", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
