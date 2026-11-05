"""Capture DAT cookies from a live Chrome profile via CDP (real user-data-dir)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.soft_admin_lib import import_dat_store, set_multi_screen, upsert_account  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
USER_DATA = Path.home() / "AppData/Local/Google/Chrome/User Data"
PORT = 9334
CDP = f"http://127.0.0.1:{PORT}"


def wait_cdp(timeout: float = 45.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests.get(CDP + "/json/version", timeout=2).status_code == 200:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.4)
    raise RuntimeError("CDP not up — is Chrome already running without debugging?")


def main() -> int:
    profile_name = sys.argv[1] if len(sys.argv) > 1 else "Profile 410"
    soft_user = sys.argv[2] if len(sys.argv) > 2 else "datshare"
    soft_pass = sys.argv[3] if len(sys.argv) > 3 else "datshare123"

    try:
        import websocket  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
        import websocket  # type: ignore

    # Must be the only Chrome using this user-data-dir
    proc = subprocess.Popen(
        [
            str(CHROME),
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={USER_DATA}",
            f"--profile-directory={profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://one.dat.com/search-loads",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_cdp()
        time.sleep(10)
        import websocket

        tabs = requests.get(CDP + "/json/list", timeout=5).json()
        ws_url = None
        for t in tabs:
            if t.get("type") == "page":
                ws_url = t["webSocketDebuggerUrl"]
                if "dat.com" in (t.get("url") or ""):
                    break
        if not ws_url:
            raise RuntimeError("no CDP page")
        ws = websocket.create_connection(ws_url, timeout=60)
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
        # Give SPA time / ensure on DAT
        call("Page.navigate", {"url": "https://one.dat.com/search-loads"})
        time.sleep(8)
        page = call(
            "Runtime.evaluate",
            {
                "expression": "({href:location.href,text:(document.body&&document.body.innerText||'').slice(0,200)})",
                "returnByValue": True,
            },
        )
        print("PAGE", page.get("result", {}).get("result", {}).get("value"))

        cookies = (call("Network.getAllCookies").get("result") or {}).get("cookies") or []
        dat = [c for c in cookies if "dat.com" in str(c.get("domain", "")).lower()]
        print(f"total cookies={len(cookies)} dat_cookies={len(dat)}")
        print(
            "names:",
            sorted({c.get("name") for c in dat})[:40],
        )

        store = []
        for c in dat:
            store.append(
                {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain"),
                    "path": c.get("path") or "/",
                    "secure": bool(c.get("secure")),
                    "httpOnly": bool(c.get("httpOnly")),
                    "expirationDate": c.get("expires"),
                }
            )

        out = ROOT / "data" / "dat_cookies_captured.json"
        out.write_text(
            json.dumps({"url": "https://one.dat.com", "lst": "{}", "sst": "", "store": store}, indent=2),
            encoding="utf-8",
        )
        print("wrote", out, "cookies", len(store))

        set_multi_screen(True)
        upsert_account(soft_user, soft_pass, streams=["one", "power"])
        import_dat_store(soft_user, "one", store, url="https://one.dat.com")
        import_dat_store(soft_user, "power", store, url="https://power.dat.com")
        print(f"Soft user ready: {soft_user} / {soft_pass}")
        return 0 if len(dat) > 0 else 1
    finally:
        # Leave Chrome running so user keeps session; only we opened with debugging
        pass


if __name__ == "__main__":
    raise SystemExit(main())
