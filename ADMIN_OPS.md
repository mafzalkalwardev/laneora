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

## Assign services (modules)

The desktop app can hold more than one module. The admin decides which ones each login sees.

| Service id | What the dispatcher sees |
| --- | --- |
| `dat` | Original module: one DAT search screen |
| `dat_dual` | Dual DAT Search: two search tabs. Searches stay separate. A refreshed login is copied to both tabs |
| `dat_3` | 3 DAT Search: three search tabs, same session copying |
| `dat_4` | 4 DAT Search: four search tabs, same session copying |

Each multi-search tab keeps its own browser profile. The tabs share the DAT session and the proxy. Existing accounts with no `services` field stay on `dat`. New users created on the admin page start on DAT Search unless you also check another module. Checking one module does not turn the others on.

On `http://127.0.0.1:8787/admin`, each user card has service checkboxes. Check the modules that login should see, then **Save services**. The dispatcher picks them up on the next Laneora login.

```powershell
python scripts\soft_admin.py set-services CLIENTUSER dat,dat_dual
python scripts\soft_admin.py set-services CLIENTUSER dat_3
python scripts\soft_admin.py set-services CLIENTUSER dat_4
python scripts\soft_admin.py status
```

`set-services CLIENTUSER dat` puts that login back on the original module only.

Four search tabs is the heavy one. Each tab is its own in-memory browser profile, and nothing is written to a Chrome profile folder. The searches stay separate. Cookies and auth tokens are copied from whichever tab refreshes the login, including on Dual DAT Search. In a local check, four tabs that reached the DAT login page used about 1.0 GB for the whole client. A signed-in search page, with the map and the load table, will use more.

## Soft server URL for clients

Clients must reach your Soft shim, e.g.:

- Same LAN: `http://YOUR_PC_LAN_IP:8787`  
- Or a VPS/public host later: `https://soft.yourdomain.com`

Give them that URL (or bake it into a `Laneora.env` / shortcut — see `CLIENT_INSTALL.md`).

## IP (Surfshark static)

- Soft `px` can stay `none` if **every client PC runs Surfshark with the same static IP** before opening DAT in Laneora.  
- Same static on admin + clients ⇒ DAT owners see that US IP.  
- Optional later: Soft `set-proxy` if you get an HTTP proxy endpoint from Surfshark/another provider.
