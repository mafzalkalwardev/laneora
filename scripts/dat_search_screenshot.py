"""
Open a Chrome copy of a local DAT-authenticated profile via CDP,
search Bloomington CA straight box loads on DAT One, save a screenshot.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "dat_bloomington_box_search.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
USER_DATA = Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data"
# Profile 53 previously had one.dat.com/search-loads auth cookies
SOURCE_PROFILE = USER_DATA / "Profile 53"
PORT = 9333
CDP = f"http://127.0.0.1:{PORT}"


def wait_cdp(timeout: float = 40.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(CDP + "/json/version", timeout=2)
            if r.status_code == 200:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    raise RuntimeError("CDP not up — is another Chrome locking the profile?")


def pick_ws() -> str:
    tabs = requests.get(CDP + "/json/list", timeout=5).json()
    for t in tabs:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page targets")


def main() -> int:
    try:
        import websocket  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
        import websocket  # type: ignore

    if not SOURCE_PROFILE.exists():
        print("missing", SOURCE_PROFILE)
        return 1

    udir = Path(tempfile.mkdtemp(prefix="laneora_dat_chrome_"))
    # Minimal Chrome user-data-dir with Default = copy of Profile 53
    default = udir / "Default"
    print("Copying profile (cookies/local storage)…")
    shutil.copytree(
        SOURCE_PROFILE,
        default,
        ignore=shutil.ignore_patterns(
            "Cache",
            "Code Cache",
            "GPUCache",
            "Service Worker",
            "ShaderCache",
            "GrShaderCache",
            "DawnGraphiteCache",
            "DawnWebGPUCache",
        ),
    )
    # Prefer First Run skipped
    (udir / "First Run").write_text("", encoding="utf-8")

    proc = subprocess.Popen(
        [
            str(CHROME),
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={udir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=ChromeWhatsNewUI",
            "https://one.dat.com/search-loads",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_cdp()
        time.sleep(8)
        import websocket

        ws = websocket.create_connection(pick_ws(), timeout=60)
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
                    if "error" in data:
                        print("CDP error", method, data["error"])
                    return data

        call("Page.enable")
        call("Runtime.enable")
        call("Page.bringToFront")
        # Wait for SPA
        for _ in range(20):
            ev = call(
                "Runtime.evaluate",
                {
                    "expression": "({href:location.href,text:(document.body&&document.body.innerText||'').slice(0,400)})",
                    "returnByValue": True,
                },
            )
            val = ev.get("result", {}).get("result", {}).get("value") or {}
            text = str(val.get("text") or "")
            print("STATE", val.get("href"), text[:120].replace("\n", " | "))
            if text and "Loading DAT One" not in text:
                break
            time.sleep(2)

        drive = r"""
(() => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const setNative = (el, val) => {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    setter?.call(el, val);
    el.dispatchEvent(new Event('input', {bubbles:true}));
    el.dispatchEvent(new Event('change', {bubbles:true}));
    el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
  };
  const hint = (el) => `${el.placeholder||''} ${el.name||''} ${el.id||''} ${el.getAttribute('aria-label')||''} ${el.getAttribute('formcontrolname')||''}`;
  return (async () => {
    await sleep(1500);
    const inputs = [...document.querySelectorAll('input, textarea')].filter(visible);
    const origin = inputs.find(i => /origin|pickup|from|city|location/i.test(hint(i))) || inputs[0];
    if (origin) {
      origin.focus();
      setNative(origin, 'Bloomington, CA');
      await sleep(800);
      // click first suggestion if any
      const opt = [...document.querySelectorAll('[role=option], .mat-option, li')].find(visible);
      if (opt) opt.click();
    }
    // equipment filters / chips
    const clickText = (re) => {
      const el = [...document.querySelectorAll('button, a, [role=button], span, div, label')]
        .filter(visible)
        .find(e => re.test((e.innerText||'').trim()));
      if (el) { el.click(); return (el.innerText||'').trim(); }
      return null;
    };
    const equipOpen = clickText(/equipment|trailer|truck type|filters/i);
    await sleep(600);
    const box = clickText(/straight\s*box|box\s*truck|SB\b|box/i);
    await sleep(400);
    const search = clickText(/search|find loads|apply|update/i);
    await sleep(5000);
    return {
      href: location.href,
      text: (document.body.innerText||'').slice(0,2500),
      clicked: {equipOpen, box, search},
      inputs: inputs.slice(0,25).map(i => hint(i).trim())
    };
  })();
})()
"""
        result = call(
            "Runtime.evaluate",
            {"expression": drive, "awaitPromise": True, "returnByValue": True},
        )
        print("DRIVE", json.dumps(result.get("result", {}).get("result", {}).get("value"), indent=2)[:5000])

        # Larger viewport then screenshot
        call("Emulation.setDeviceMetricsOverride", {
            "width": 1440,
            "height": 900,
            "deviceScaleFactor": 1,
            "mobile": False,
        })
        time.sleep(1)
        shot = call("Page.captureScreenshot", {"format": "png", "fromSurface": True, "captureBeyondViewport": False})
        b64 = (shot.get("result") or {}).get("data")
        if not b64:
            print("no screenshot", shot)
            return 1
        OUT.write_bytes(base64.b64decode(b64))
        print("SAVED", OUT, "bytes", OUT.stat().st_size)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:  # noqa: BLE001
            proc.kill()
        shutil.rmtree(udir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
