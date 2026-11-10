# Laneora admin operations (you)

## What you run (your PC / server)

1. Soft shim (auth + DAT cookies for all Soft users):

```powershell
cd "d:\Dispatch Softwares\Laneora"
.\.venv\Scripts\Activate.ps1
$env:LANEORA_SOFT_HOST="0.0.0.0"
$env:LANEORA_SOFT_PORT="8787"
python server\soft_shim.py
```

Or double-click `Start Soft Server.bat`.

2. Keep **Surfshark static US IP ON** on this machine when you refresh DAT cookies (and on client PCs when they open DAT, unless you later set Soft `set-proxy`).

## Two DAT searches

The original plans stay one search. Plans whose id ends in `_x2` are the same lengths with two searches inside one Laneora window. Existing accounts do not gain a second tab until you apply an `_x2` plan. Both tabs use the one shared DAT session already on that account. They do not add a second Soft login.

A build that still speaks the old authenticate response ignores `max_searches` and keeps a single search.

```powershell
python -m unittest tests/test_two_searches.py tests/test_shayan_password_hash.py -v
```

Package with `build.ps1` and entry `app\main.py`. Do not point PyInstaller at a script that imports `server`. A frozen exe that does that stops with `No module named server`. `app/search_tabs.py` does not import `server`. Dispatcher PCs should keep `LANEORA_SOFT_FALLBACK=0` so the client does not try to start a local shim.

## Create / manage Soft users (client logins)

```powershell
python scripts\soft_admin.py add-user CLIENTUSER CLIENTPASS
python scripts\soft_admin.py status
python scripts\soft_admin.py multi-screen off
```

- `add-user` → creates Soft login you give to a client  
- `multi-screen off` → same Soft login, **one live PC at a time** (newest wins)  
- Users live in `data\local_users.json`  
- Soft roster dropdown also: `python scripts\add_user.py USER PASS`

## Refresh DAT session (do this on a schedule)

1. On **this** PC: Surfshark static IP **ON**  
2. Chrome (Daniel / DAT profile) open → log into DAT → **Search Loads** fully loaded  
3. Capture + push to **all** Soft users:

```powershell
# Chrome must be started with debugging OR already on port 9334
# If needed:
#   close Chrome, then:
#   chrome.exe --remote-debugging-port=9334 --remote-allow-origins=* --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" --profile-directory="Profile 410" https://one.dat.com/search-loads

python scripts\capture_dat_from_cdp.py 9334 datshare datshare123
python scripts\soft_admin.py push-capture
python scripts\soft_admin.py multi-screen off
```

### Suggested refresh times

| When | Why |
|------|-----|
| **Every 4–6 hours** while clients are working | DAT Auth0 cookies expire; safest cadence |
| **Morning before shift** | Clean start for the day |
| **Whenever a client says DAT kicked them / login page** | Immediate recapture + `push-capture` |

Clients pick up the new cookies on **next Soft login** or **Reconnect!** in Laneora.

## Soft server URL for clients

Clients must reach your Soft shim, e.g.:

- Same LAN: `http://YOUR_PC_LAN_IP:8787`  
- Or a VPS/public host later: `https://soft.yourdomain.com`

Give them that URL (or bake it into a `Laneora.env` / shortcut — see `CLIENT_INSTALL.md`).

## IP (Surfshark static)

- Soft `px` can stay `none` if **every client PC runs Surfshark with the same static IP** before opening DAT in Laneora.  
- Same static on admin + clients ⇒ DAT owners see that US IP.  
- Optional later: Soft `set-proxy` if you get an HTTP proxy endpoint from Surfshark/another provider.
