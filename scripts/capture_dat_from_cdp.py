"""Capture DAT cookies from an already-running Chrome CDP on port 9334."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.soft_admin_lib import import_dat_store, upsert_account  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9334
SOFT_USER = sys.argv[2] if len(sys.argv) > 2 else "datshare"
SOFT_PASS = sys.argv[3] if len(sys.argv) > 3 else "datshare123"
CDP = f"http://127.0.0.1:{PORT}"


def main() -> int:
    import websocket

    # Prefer a DAT page; else create one
    tabs = requests.get(CDP + "/json/list", timeout=5).json()
    target = None
    for t in tabs:
        if t.get("type") == "page" and "dat.com" in (t.get("url") or ""):
            target = t
            break
    if target is None:
        # open new tab via /json/new
        try:
            target = requests.put(
                CDP + "/json/new?" + requests.utils.quote("https://one.dat.com/search-loads", safe=""),
                timeout=10,
            ).json()
        except Exception:  # noqa: BLE001
            target = requests.get(
                CDP + "/json/new?https://one.dat.com/search-loads",
                timeout=10,
            ).json()
        time.sleep(5)
        tabs = requests.get(CDP + "/json/list", timeout=5).json()
        for t in tabs:
            if t.get("type") == "page" and "dat.com" in (t.get("url") or ""):
                target = t
                break
    if not target:
        # fallback first page
        pages = [t for t in tabs if t.get("type") == "page"]
        if not pages:
            print("no pages")
            return 1
        target = pages[0]

    print("using tab", target.get("title"), target.get("url"))
    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=60)
    msg_id = 0

    def call(method: str, params: dict | None = None):
        nonlocal msg_id
        msg_id += 1
        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        ws.send(json.dumps(payload))
        while True:
            data = json.loads(ws.recv())
            if data.get("id") == msg_id:
                return data

    call("Network.enable")
    call("Page.enable")
    call("Page.navigate", {"url": "https://one.dat.com/search-loads"})
    time.sleep(10)
    page = call(
        "Runtime.evaluate",
        {
            "expression": "({href:location.href,text:(document.body&&document.body.innerText||'').slice(0,300)})",
            "returnByValue": True,
        },
    )
    print("PAGE", page.get("result", {}).get("result", {}).get("value"))

    cookies = (call("Network.getAllCookies").get("result") or {}).get("cookies") or []
    dat = [c for c in cookies if "dat.com" in str(c.get("domain", "")).lower()]
    print(f"total={len(cookies)} dat={len(dat)}")
    print("names", sorted({c.get("name") for c in dat})[:50])

    store = [
        {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain"),
            "path": c.get("path") or "/",
            "secure": bool(c.get("secure")),
            "httpOnly": bool(c.get("httpOnly")),
            "expirationDate": c.get("expires"),
        }
        for c in dat
    ]
    out = ROOT / "data" / "dat_cookies_captured.json"
    out.write_text(
        json.dumps({"url": "https://one.dat.com", "lst": "{}", "sst": "", "store": store}, indent=2),
        encoding="utf-8",
    )
    print("wrote", out, len(store))

    upsert_account(SOFT_USER, SOFT_PASS, streams=["one", "power"])
    import_dat_store(SOFT_USER, "one", store, url="https://one.dat.com")
    import_dat_store(SOFT_USER, "power", store, url="https://power.dat.com")
    print(f"Soft login: {SOFT_USER} / {SOFT_PASS}")
    print("Tip: run soft_admin.py push-capture to copy this jar to ALL Soft users.")
    return 0 if dat else 1


if __name__ == "__main__":
    raise SystemExit(main())
