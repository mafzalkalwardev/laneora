# Laneora

Laneora is a Windows desktop client for DAT board streams. It signs in against `soft.awwthat.com`, selects a stream, applies the assigned HTTP proxy, and opens embedded Chromium tabs (Qt WebEngine) for DAT One / DAT Power workflows.

**New private GitHub repo:** https://github.com/mafzalkalwardev/laneora  
This project is separate from the older Awwthat Pro folder/repo — that tree was left untouched.

## Features
- Login + subscription/stream limits (`/authenticate`, `/logger`)
- Stream picker with per-stream encrypted session payloads
- HTTP proxy injection (`px` / `pu` / `pd` + port `p`)
- Embedded browser tabs (Chrome UA, usurpModal remover JS)
- Cookie + localStorage session restore
- Timezone sync via `ipinfo.io` + Windows `tzutil`
- Speedtest tab (`fast.com`)
- AES/CryptoJS-compatible decrypt helpers
- Auto-update check (`/latest_version`, `/update`)

## Setup (Windows)
```powershell
cd "d:\Dispatch Softwares\Laneora"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\make_brand.py
```

Or double-click `Start Laneora.bat` (starts local API + app).

## Local test logins (default)
The app talks to a **local Soft-compatible API** at `http://127.0.0.1:8787` by default.

| Username | Password | Streams |
|----------|----------|---------|
| `admin`  | `admin123` | one, power |
| `tester` | `test123`  | one |

Start API, then app:
```powershell
# terminal 1
python server\local_api.py

# terminal 2
python -m app
```

### Inject your own users
```powershell
python scripts\add_user.py myuser mypass
python scripts\add_user.py dispatcher secret --streams one,power
```
Users are stored in `data/users.json` (edit freely). Restart is not required for new users on next login.

### Point at real soft.awwthat.com (or your future host)
```powershell
$env:LANEORA_SERVER_URL = "https://soft.awwthat.com"
$env:LANEORA_SKIP_UPDATE = "0"
python -m app
```

## Test checklist
1. Start `server\local_api.py`
2. Run `python -m app`
3. Login as `admin` / `admin123`
4. Open a stream — DAT tabs should load (direct / no proxy in local mode)
5. Confirm SpeedTest tab and reconnect

## Optional EXE build
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

## Notes
- API host remains `https://soft.awwthat.com` so existing credentials work.
- Large reference EXE is gitignored under `_reference/`.
- Recovery evidence lives in `recovery/` (disassembly + notes), not required at runtime.
