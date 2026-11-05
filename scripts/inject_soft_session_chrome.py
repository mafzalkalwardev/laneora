"""Inject Soft DAT cookies into the session-share Chrome (CDP 9444). No DAT username/password."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import PASSPHRASE  # noqa: E402
from app.auth import authenticate  # noqa: E402
from app.crypto_util import decrypt  # noqa: E402

if len(sys.argv) < 4:
    print("usage: inject_soft_session_chrome.py PORT USERNAME PASSWORD")
    raise SystemExit(2)
PORT = int(sys.argv[1])
USER = sys.argv[2]
PASS = sys.argv[3]
CDP = f"http://127.0.0.1:{PORT}"
TARGET = "https://one.dat.com/search-loads"


def main() -> int:
    print("Soft login", USER)
    session = authenticate(USER, PASS)
    full = json.loads(decrypt(PASSPHRASE, session.resp["one"]))
    store = full.get("store") or []
    print(f"cookies from Soft: {len(store)}")

    tabs = requests.get(CDP + "/json/list", timeout=10).json()
    page = next((t for t in tabs if t.get("type") == "page"), None)
    if not page:
        print("no CDP page — is session Chrome open on", PORT, "?")
        return 1
    print("using", page.get("title"), page.get("url"))

    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60)
    mid = 0

    def call(method: str, params: dict | None = None) -> dict:
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            data = json.loads(ws.recv())
            if data.get("id") == mid:
                return data

    call("Network.enable")
    call("Page.enable")
    call("Network.clearBrowserCookies")
    ok = 0
    for c in store:
        params = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain") or ".dat.com",
            "path": c.get("path") or "/",
            "secure": bool(c.get("secure")),
            "httpOnly": bool(c.get("httpOnly")),
        }
        if c.get("expirationDate"):
            params["expires"] = float(c["expirationDate"])
        if (call("Network.setCookie", params).get("result") or {}).get("success"):
            ok += 1
    print(f"injected {ok}/{len(store)}")

    call("Page.navigate", {"url": TARGET})
    time.sleep(12)
    info = call(
        "Runtime.evaluate",
        {
            "expression": "({href:location.href,title:document.title,text:(document.body&&document.body.innerText||'').slice(0,500)})",
            "returnByValue": True,
        },
    )
    val = (info.get("result") or {}).get("result", {}).get("value")
    print("PAGE", json.dumps(val, indent=2)[:900])
    href = (val or {}).get("href") or ""
    text = ((val or {}).get("text") or "").lower()
    blocked = "you have been blocked" in text or "attention required" in ((val or {}).get("title") or "").lower()
    logged = "one.dat.com" in href and "login.dat.com" not in href and not blocked and (
        "search loads" in text or "new search" in text or "my trucks" in text or "dashboard" in text
    )
    print("BLOCKED", blocked)
    print("LOGGED_IN_UI", logged)
    ws.close()
    return 0 if logged else 2


if __name__ == "__main__":
    raise SystemExit(main())
