<div align="center">

<img src="app/resources/logo.png" alt="Laneora logo" width="220" />

# Laneora

**DAT load-board stream client for truck dispatch teams**

Windows desktop app for DAT One. Clients sign in with a Soft username, then open Search Loads. You manage those logins and their plans from the admin dashboard.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/UI-PyQt5%20WebEngine-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)](#setup-windows)
[![License](https://img.shields.io/badge/License-MIT-green)](https://github.com/mafzalkalwardev/laneora)
[![Release](https://img.shields.io/badge/Release-v3.0.0-F5A524)](https://github.com/mafzalkalwardev/laneora/releases)
[![GitHub](https://img.shields.io/badge/GitHub-Public-181717?logo=github)](https://github.com/mafzalkalwardev/laneora)

[Features](#features) · [Quick start](#setup-windows) · [Admin](#admin-dashboard) · [Client](#client-login)

</div>

---

## Why Laneora?

Laneora is a Windows client for dispatch teams who work **DAT One Search Loads**. The client does not ask for a DAT username. It signs in to the Laneora Soft server, receives the shared DAT session, and opens Search Loads.

You run the Soft server on your PC (or later on a VPS). The admin dashboard on that server is where you create users and set how long they can sign in.

**Repository:** https://github.com/mafzalkalwardev/laneora

---

## Features

| Area | What you get |
|------|----------------|
| Client | Centered login, then one **Load DAT Stream** button for DAT One Search Loads |
| Soft server | `Start Soft Server.bat` — auth, heartbeat, and the shared DAT cookie session on port 8787 |
| Admin | Browser dashboard to create users, set passwords, and turn accounts on or off |
| Plans | Trial 1 hour, 1 day, 1 week, 15 days, 1 month, 3 months, 6 months, 1 year |
| Session | DAT cookies are pushed to every Soft user. The client does not log in to DAT itself |
| Screen | One Laneora window per Soft username. Side menu, COI banner, and Connect Email are hidden |

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

Or double-click `Start Soft Server.bat`, then `Start Laneora.bat`.

**Requirements:** Windows 10/11, Python 3.12+.

---

## Admin dashboard

With the Soft server running, open:

- This PC: http://127.0.0.1:8787/admin
- Another PC on the same network: `http://YOUR_LAN_IP:8787/admin`

Sign in with the dashboard username and password from `data/soft_config.json` (`dashboard`). The first run creates `admin` / `admin123` if that block is missing. Changing it here does not change a Soft client user who happens to be named admin.

From the dashboard:

1. Create a username, password, and plan. The new account receives the DAT cookies in `data/dat_cookies_captured.json`.
2. **Apply from now** starts that plan immediately.
3. **Add onto current** adds the same length onto time still left.
4. Disable, change the password, or delete the user.

Accounts with no plan can still log in. After a plan’s end time, the next Laneora login is refused. A window that is already open stays open until that user signs in again.

There is no account cap. The same Soft username cannot stay open on two Laneora screens at once.

---

## Client login

The Laneora window shows the logo, the name, username, password, and Login. After a correct Soft login the dialog says **Login Successful**, then one button: **Load DAT Stream**.

Client machines use `dist\Laneora.exe` with `dist\Laneora Soft.bat`. That bat must point at the PC running the Soft server, for example `http://192.168.1.20:8787`. Each client PC needs the same Surfshark static US IP as the machine that captured the DAT cookies. Do not click **Login Anyway** on DAT.

---

## Same IP on many PCs

Every client PC uses the same Surfshark static US IP before opening DAT. With that, Soft `px` stays `none` and DAT sees the static IP.

A shared HTTP proxy is optional. If you have one, Soft can send it to every account:

```powershell
# Allow same Soft user on many PCs (no "Multiple Screens not allowed")
python scripts\soft_admin.py multi-screen on

# Point ALL Soft accounts at one shared proxy (required for same IP)
python scripts\soft_admin.py set-proxy PROXY_HOST PROXY_PORT PROXY_USER PROXY_PASS

# Confirm what DAT would see
python scripts\soft_admin.py check-ip

# Soft account + import a DAT cookie jar (optional; see data/dat_cookies.example.json)
python scripts\soft_admin.py add-user dispatcher1 secret
python scripts\soft_admin.py import-store dispatcher1 one data\dat_cookies.json

python scripts\soft_admin.py status
```

Config: [`data/soft_config.json`](data/soft_config.json) · accounts: [`data/local_users.json`](data/local_users.json)

Without the shared Surfshark IP, or without a real proxy, each PC shows its own public IP to DAT.  

---

## Soft server

```powershell
# window stays open — this is what clients log in to
.\Start Soft Server.bat
```

Or:

```powershell
$env:LANEORA_SOFT_HOST = "0.0.0.0"
$env:LANEORA_SOFT_PORT = "8787"
python server\soft_shim.py
```

Point the client at that server:

```powershell
$env:LANEORA_SERVER_URL = "http://127.0.0.1:8787"
python -m app
```

Closing the Laneora window does not stop other clients. Stopping the Soft server, or letting this PC sleep, stops new logins.

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

1. Start the Soft server and open http://127.0.0.1:8787/admin  
2. Sign in. The login card goes away and the user list is the page  
3. Create a user with a plan, or use an existing Soft user that has no plan yet  
4. Run `python -m app`, sign in, and choose **Load DAT Stream**  
5. Confirm Search Loads opens and an expired plan is refused on the next login  

---

## Optional EXE build

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Output: `dist\Laneora.exe`

---

## Architecture (short)

```text
Admin dashboard  →  Soft server (users, plans, DAT cookies)
Client login     →  Soft /authenticate + /logger
Load DAT Stream  →  Qt WebEngine opens DAT One Search Loads
```

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

- The Soft server in this repo is the login service clients use. `soft.awwthat.com` is not required.  
- Account passwords and captured DAT cookies stay in `data/` on the machine running the server. Do not commit those files.  
- Large binaries are gitignored (`dist/`, `*.exe`).  
- More operator steps are in `ADMIN_OPS.md` and `CLIENT_INSTALL.md`.  

---

<div align="center">

**Laneora** — DAT board streams for dispatch teams

</div>
