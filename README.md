# Laneora

Laneora is a Windows desktop client for DAT board streams. It signs in against **`soft.awwthat.com`** (source of truth for admin, streams, proxies, cookies), then opens embedded Chromium tabs (Qt WebEngine) for DAT One / DAT Power workflows.

**Private GitHub repo:** https://github.com/mafzalkalwardev/laneora  

## Features
- Login + subscription/stream limits (`/authenticate`, `/logger`) against soft.awwthat.com
- Local **credentials roster** so you can inject multiple soft accounts for testing
- Stream picker with per-stream encrypted session payloads from soft
- HTTP proxy injection (`px` / `pu` / `pd` + port `p`)
- Embedded browser tabs (Chrome UA, usurpModal remover JS)
- Cookie + localStorage session restore
- Timezone sync via `ipinfo.io` + Windows `tzutil`
- Speedtest tab (`fast.com`)
- AES/CryptoJS-compatible decrypt helpers
- Auto-update check (`/latest_version`, `/update`) with safe version compare

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

## Inject soft users for testing
Laneora **does not create accounts on soft.awwthat.com**. It stores credentials locally and uses them to log into soft.

```powershell
python scripts\add_user.py yourSoftUser yourSoftPass
python scripts\add_user.py anotherUser anotherPass --label "Dispatcher 2"
```

Roster file: [`data/users.json`](data/users.json)

In the login UI:
1. Pick an injected user from the dropdown (autofills username/password), or type manually
2. Click **Login** — authenticates against `https://soft.awwthat.com`
3. Successful logins are also saved to the roster automatically
4. Use **Save current to roster** to store typed credentials without waiting for login

## Point at your future host (later)
```powershell
$env:LANEORA_SERVER_URL = "https://api.yourdomain.com"
python -m app
```

Optional offline stub (not used by default): `python server\local_api.py` then  
`$env:LANEORA_SERVER_URL = "http://127.0.0.1:8787"`.

Skip remote update download:
```powershell
$env:LANEORA_SKIP_UPDATE = "1"
```

## Test checklist
1. Inject at least one real soft.awwthat.com account via `scripts/add_user.py`
2. Run `python -m app`
3. Select the user (or type soft admin credentials)
4. Confirm streams/proxy come from soft and DAT tabs load
5. Confirm SpeedTest + reconnect

## Optional EXE build
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

## Notes
- Soft remains the source of truth until you seed your own admin/API.
- Large reference EXE is gitignored under `_reference/`.
- Recovery evidence lives in `recovery/` (not required at runtime).
