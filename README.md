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
python -m app
```

## Test with your accounts
1. Run `python -m app`
2. Sign in with a known-good `soft.awwthat.com` username/password
3. Confirm stream buttons appear from `active_subs`
4. Open a stream — proxy should apply; DAT tabs should load
5. Confirm cookies/localStorage restore, SpeedTest tab, and reconnect

## Optional EXE build
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

## Notes
- API host remains `https://soft.awwthat.com` so existing credentials work.
- Large reference EXE is gitignored under `_reference/`.
- Recovery evidence lives in `recovery/` (disassembly + notes), not required at runtime.
