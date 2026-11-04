<div align="center">

<img src="app/resources/logo.png" alt="Laneora logo" width="220" />

# Laneora

**DAT load-board stream client for truck dispatch teams**

Windows desktop app for DAT One / DAT Power workflows — Soft auth, proxied WebEngine tabs, multi-account roster, session restore.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/UI-PyQt5%20WebEngine-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)](#setup-windows)
[![License](https://img.shields.io/badge/License-MIT-green)](https://github.com/mafzalkalwardev/laneora)
[![Release](https://img.shields.io/badge/Release-v3.0.0-F5A524)](https://github.com/mafzalkalwardev/laneora/releases)
[![GitHub](https://img.shields.io/badge/GitHub-Public-181717?logo=github)](https://github.com/mafzalkalwardev/laneora)

[Features](#features) · [Quick start](#setup-windows) · [Inject soft users](#inject-soft-users-for-testing) · [Keywords](#seo--keywords)

</div>

---

## Why Laneora?

Laneora (lane + aura) is a modern Windows client for **freight dispatch** teams who work DAT load boards through Soft-managed streams. Sign in once, pick a stream, and Laneora applies the assigned HTTP proxy, restores cookies / localStorage, and opens DAT in an embedded Chromium browser — built for day-to-day **truck dispatch**, **load board**, and **DAT One / DAT Power** use.

Auth, subscriptions, proxies, and encrypted stream payloads come from **`soft.awwthat.com`** (source of truth). A local credentials roster lets you inject multiple Soft accounts for testing before you host your own admin API.

**Repository:** https://github.com/mafzalkalwardev/laneora

---

## Features

| Area | What you get |
|------|----------------|
| Soft auth | `/authenticate` + `/logger` heartbeat, subscription / multi-screen limits |
| Streams | Stream picker with Soft-encrypted session payloads |
| Proxy | Per-stream HTTP proxy (`px` / `pu` / `pd` + port `p`) |
| Browser | PyQt5 Qt WebEngine tabs, Chrome UA, DAT usurpModal cleanup |
| Session | Cookie injection + localStorage restore |
| Ops extras | Timezone sync (`ipinfo` + `tzutil`), Speedtest (`fast.com`), auto-update check |
| Testing | Local Soft user roster — inject accounts without changing Soft’s database |

---

## Setup (Windows)

```powershell
cd "d:\Dispatch Softwares\Laneora"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\make_brand.py
python -m app
```

Or double-click `Start Laneora.bat`.

**Requirements:** Windows 10/11, Python 3.12+, network access to Soft and DAT.

---

## Inject Soft users for testing

Laneora does **not** create accounts on `soft.awwthat.com`. It stores Soft credentials locally and uses them to log into Soft.

```powershell
python scripts\add_user.py yourSoftUser yourSoftPass
python scripts\add_user.py anotherUser anotherPass --label "Dispatcher 2"
```

Roster file: [`data/users.json`](data/users.json)

In the login UI:

1. Pick an injected user from the dropdown (autofills username/password), or type Soft credentials manually  
2. Click **Login** — authenticates against `https://soft.awwthat.com`  
3. Successful logins are saved to the roster automatically  
4. Use **Save current to roster** to store typed credentials without waiting for login  

---

## Point at your future host

When you seed your own admin / API:

```powershell
$env:LANEORA_SERVER_URL = "https://api.yourdomain.com"
python -m app
```

Optional Soft-compatible offline stub (accounts in `data/local_users.json`):

```powershell
python server\local_api.py
$env:LANEORA_SERVER_URL = "http://127.0.0.1:8787"
python -m app
```

Multi-account Soft health + DAT URL decrypt check:

```powershell
python scripts\test_soft_and_accounts.py
```

Skip remote update download:

```powershell
$env:LANEORA_SKIP_UPDATE = "1"
```

---

## Test checklist

1. Inject at least one real Soft account via `scripts/add_user.py`  
2. Run `python -m app`  
3. Select the user (or type Soft admin credentials)  
4. Confirm streams / proxy come from Soft and DAT tabs load  
5. Confirm SpeedTest + reconnect  

---

## Optional EXE build

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Output: `dist\Laneora.exe`

---

## Architecture (short)

```text
Login UI  →  soft.awwthat.com (/authenticate, /logger)
         →  stream + HTTP proxy
         →  Qt WebEngine (DAT One / DAT Power + session restore)
```

Soft remains the source of truth until you replace it with your own backend.

---

## SEO / keywords

**Primary:** Laneora, DAT board client, DAT One desktop app, DAT Power browser, truck dispatch software, load board stream client, Soft awwthat client, freight dispatch Windows app  

**Secondary:** PyQt5 WebEngine DAT, HTTP proxy load board, multi-account Soft roster, dispatch session restore, usurpModal cleaner, ipinfo timezone dispatch, Soft authenticate logger  

**Related:** trucking TMS companion, carrier dispatch tooling, load board automation desktop, Qt Chromium DAT login  

---

## Release

Current product version: **v3.0.0** (see [Releases](https://github.com/mafzalkalwardev/laneora/releases)).

---

## Notes

- Soft remains the source of truth until you seed your own admin/API.  
- If login shows **Soft server error (HTTP 500)**, Soft’s `/authenticate` route is failing on the server (Laneora roster injection is fine). Other Soft routes like `/latest_version` may still work.  
- Large reference binaries are gitignored (`_reference/`, `*.exe`).  
- Recovery / reverse-engineering notes live in `recovery/` (not required at runtime).  

---

<div align="center">

**Laneora** — DAT board streams for dispatch teams

</div>
