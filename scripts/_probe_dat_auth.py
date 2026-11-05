import json
import time

import requests
import websocket

CDP = "http://127.0.0.1:9334"
ver = requests.get(CDP + "/json/version", timeout=5).json()
ws = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=60)
mid = 0


def call(method, params=None):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        data = json.loads(ws.recv())
        if data.get("id") == mid:
            return data


tabs = requests.get(CDP + "/json/list", timeout=5).json()
for t in tabs:
    print("TAB", t.get("type"), (t.get("title") or "")[:80], "|", (t.get("url") or "")[:140])

created = call("Target.createTarget", {"url": "https://one.dat.com/dashboard"})
print("created", created.get("result"))
time.sleep(7)
tabs = requests.get(CDP + "/json/list", timeout=5).json()
page = None
for t in tabs:
    if t.get("type") != "page":
        continue
    url = t.get("url") or ""
    print("PAGE-TAB", (t.get("title") or "")[:60], "|", url[:140])
    if "one.dat.com" in url and "login" not in url:
        page = t
if page is None:
    page = next((t for t in tabs if t.get("type") == "page" and "dat.com" in (t.get("url") or "")), None)

if not page:
    raise SystemExit("no page")

print("CHOSEN", page.get("title"), page.get("url")[:160])


class P:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=60)
        self.mid = 0

    def call(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == self.mid:
                return data


p = P(page["webSocketDebuggerUrl"])
info = p.call(
    "Runtime.evaluate",
    {
        "expression": "({href:location.href,title:document.title,text:(document.body&&document.body.innerText||'').slice(0,500)})",
        "returnByValue": True,
    },
)
print("EVAL", info.get("result", {}).get("result", {}).get("value"))
cookies = (p.call("Network.getAllCookies").get("result") or {}).get("cookies") or []
# Network not enabled — enable then retry
p.call("Network.enable")
cookies = (p.call("Network.getAllCookies").get("result") or {}).get("cookies") or []
dat = [c for c in cookies if "dat.com" in str(c.get("domain", "")).lower()]
print("dat", len(dat), "auth0", [len(c.get("value") or "") for c in dat if c.get("name") == "auth0"])
p.ws.close()
ws.close()
