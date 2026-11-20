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

## Load search API

Any app that can reach the Soft server can search loads. It uses the board session already stored in Laneora (the same login the desktop window opens). It cannot create users, change a plan, or call the admin desk. Those stay on `http://127.0.0.1:8787/admin`.

Base URL: `http://127.0.0.1:8787` on this PC, or `http://YOUR_PC_LAN_IP:8787` from another machine.

```powershell
$base = "http://127.0.0.1:8787"
$login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/session" -ContentType "application/json" -Body '{"username":"CLIENTUSER","password":"CLIENTPASS"}'
$headers = @{ Authorization = "Bearer $($login.token)" }
$body = @{
  origin = @{ city = "Dallas"; state = "TX"; deadhead_miles = 100 }
  destination = @{ city = "Atlanta"; state = "GA"; deadhead_miles = 150 }
  equipment = @("V")
  capacity = "FULL"
  max_age_minutes = 240
} | ConvertTo-Json
$found = Invoke-RestMethod -Method Post -Uri "$base/api/v1/loads/search" -Headers $headers -ContentType "application/json" -Body $body
$found.loads[0] | Format-List company, phone, rate, miles, origin, destination
Invoke-RestMethod -Uri "$base/api/v1/loads/detail?search_id=$($found.search_id)&match_id=$($found.loads[0].id)" -Headers $headers
```

`X-API-Key: <token>` works in place of the Authorization header. Each load includes company, phone, email, rate, miles, equipment, weight, credit, comments, and a `detail` object with the full board record. The detail route adds the DOT and MC numbers and the peer rating.

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| GET | `/api/v1` | no | Route index |
| GET | `/api/v1/health` | no | Server is up |
| POST | `/api/v1/session` | no | Laneora username and password. Returns a loads-only token |
| POST | `/api/v1/loads/search` | yes | Search. Body: `origin`, optional `destination`, `equipment`, `capacity`, `earliest`, `latest`, `max_age_minutes`, `limit` |
| GET | `/api/v1/loads/detail` | yes | Query `search_id` and `match_id` from a search result |

Origin and destination are `{city, state, deadhead_miles}` or `{states: ["TX","OK"]}`. Equipment accepts `V`, `R`, `F`, `van`, `reefer`, `flatbed`. A disabled or expired Laneora login cannot get a token. If no board session has been captured, search returns 409. The response never includes the board token or cookies.

## Soft server URL for clients

Clients must reach your Soft shim, e.g.:

- Same LAN: `http://YOUR_PC_LAN_IP:8787`  
- Or a VPS/public host later: `https://soft.yourdomain.com`

Give them that URL (or bake it into a `Laneora.env` / shortcut — see `CLIENT_INSTALL.md`).

## IP (Surfshark static)

- Soft `px` can stay `none` if **every client PC runs Surfshark with the same static IP** before opening DAT in Laneora.  
- Same static on admin + clients ⇒ DAT owners see that US IP.  
- Optional later: Soft `set-proxy` if you get an HTTP proxy endpoint from Surfshark/another provider.
