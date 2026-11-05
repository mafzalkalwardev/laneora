"""Capture DAT cookies from already-running Chrome CDP — no restart, no navigate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.soft_admin_lib import import_dat_store, upsert_account  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9334
CDP = f"http://127.0.0.1:{PORT}"


class Cdp:
    def __init__(self, url: str) -> None:
        self.ws = websocket.create_connection(url, timeout=60)
        self.mid = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == self.mid:
                return data

    def close(self) -> None:
        self.ws.close()


def score_tab(t: dict) -> int:
    url = (t.get("url") or "").lower()
    title = (t.get("title") or "").lower()
    if t.get("type") != "page":
        return -100
    if "login.dat.com" in url or "login" in title and "dat" in title:
        return 1
    if "one.dat.com/search-loads" in url or "search loads" in title:
        return 100
    if "one.dat.com/dashboard" in url or title.startswith("dashboard"):
        return 90
    if "one.dat.com" in url or "power.dat.com" in url:
        return 50
    if "dat.com" in url:
        return 10
    return 0


def main() -> int:
    ver = requests.get(CDP + "/json/version", timeout=5).json()
    browser = Cdp(ver["webSocketDebuggerUrl"])

    # Prefer browser-level cookie jar (all hosts) — no navigation
    cookies = (browser.call("Storage.getCookies").get("result") or {}).get("cookies") or []

    tabs = requests.get(CDP + "/json/list", timeout=5).json()
    pages = sorted(tabs, key=score_tab, reverse=True)
    page = pages[0] if pages and score_tab(pages[0]) > 0 else None

    if page and page.get("webSocketDebuggerUrl"):
        print("using tab", page.get("title"), page.get("url"))
        page_cdp = Cdp(page["webSocketDebuggerUrl"])
        page_cdp.call("Network.enable")
        page_cdp.call("Page.enable")
        info = page_cdp.call(
            "Runtime.evaluate",
            {
                "expression": "({href:location.href,text:(document.body&&document.body.innerText||'').slice(0,300)})",
                "returnByValue": True,
            },
        )
        print("PAGE", (info.get("result") or {}).get("result", {}).get("value"))
        # Prefer page Network.getAllCookies if it returns anything; else keep browser jar
        page_cookies = (page_cdp.call("Network.getAllCookies").get("result") or {}).get("cookies") or []
        if page_cookies:
            cookies = page_cookies
        page_cdp.close()

    browser.close()

    dat = [c for c in cookies if "dat.com" in str(c.get("domain", "")).lower()]
    print(f"total={len(cookies)} dat={len(dat)}")
    print("names", sorted({c.get("name") for c in dat}))

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
        json.dumps(
            {
                "url": "https://one.dat.com",
                "lst": "{}",
                "sst": "",
                "source_profile": "Profile 1",
                "source": "cdp-live-profile1",
                "store": store,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", out, len(store))
    for need in ("auth0", "did", "cf_clearance", "auth0_compat"):
        hits = [c for c in store if c["name"] == need]
        print(need, "n", len(hits), "lens", [len(c.get("value") or "") for c in hits])

    if not dat:
        return 1

    upsert_account("datshare", "datshare123", streams=["one", "power"])
    import_dat_store("datshare", "one", store, url="https://one.dat.com")
    import_dat_store("datshare", "power", store, url="https://power.dat.com")
    print("imported Soft user datshare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
