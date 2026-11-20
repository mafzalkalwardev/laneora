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

## HTTP API

Same process as the admin desk, for any HTTP client. Base URL is the Soft server, for example `http://127.0.0.1:8787` on this PC or `http://YOUR_PC_LAN_IP:8787` from another machine. The server already binds `0.0.0.0:8787`.

`GET /api/v1` returns the route list. No token required for that, for `GET /api/v1/health`, or for `POST /api/v1/session`.

```powershell
$base = "http://127.0.0.1:8787"
$login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/session" -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
$token = $login.token
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod -Uri "$base/api/v1/catalog" -Headers $headers
Invoke-RestMethod -Method Post -Uri "$base/api/v1/users" -Headers $headers -ContentType "application/json" -Body '{"username":"CLIENTUSER","password":"CLIENTPASS","plan":"day_1","services":["dat"]}'
Invoke-RestMethod -Method Patch -Uri "$base/api/v1/users/CLIENTUSER" -Headers $headers -ContentType "application/json" -Body '{"plan":"week_1","extend":true,"services":["dat","dat_dual"]}'
Invoke-RestMethod -Method Delete -Uri "$base/api/v1/users/CLIENTUSER" -Headers $headers
```

`X-API-Key: <token>` is accepted in place of the Authorization header. Browser clients on another origin can call it; responses send `Access-Control-Allow-Origin: *`.

| Method | Path | Auth | Body |
| --- | --- | --- | --- |
| GET | `/api/v1` | no | Route index |
| GET | `/api/v1/health` | no | Server is up, account count |
| POST | `/api/v1/session` | no | `username`, `password` of the dashboard login. Returns `token` |
| GET | `/api/v1/catalog` | yes | Plans and service ids |
| GET | `/api/v1/users` | yes | Accounts, including each Laneora password |
| POST | `/api/v1/users` | yes | `username`, `password`, `plan`, optional `services` |
| GET | `/api/v1/users/{username}` | yes | One account |
| PATCH | `/api/v1/users/{username}` | yes | Any of `password`, `plan`, `extend`, `active`, `services` |
| DELETE | `/api/v1/users/{username}` | yes | Removes the account |
| POST | `/api/v1/token/rotate` | yes | Returns a new token. The old one stops working |

Plan ids: `trial_1h`, `day_1`, `week_1`, `days_15`, `month_1`, `months_3`, `months_6`, `year_1`.

Service ids: `dat`, `dat_dual`, `dat_3`, `dat_4`.

Set `LANEORA_API_TOKEN` before starting the server to choose the token yourself. While that variable is set, rotate is refused. The token is otherwise saved in `data/soft_config.json` as `api_token`. The desktop client still uses `/authenticate` and `/logger`. This API does not return the board cookie jar.

## Soft server URL for clients

Clients must reach your Soft shim, e.g.:

- Same LAN: `http://YOUR_PC_LAN_IP:8787`  
- Or a VPS/public host later: `https://soft.yourdomain.com`

Give them that URL (or bake it into a `Laneora.env` / shortcut — see `CLIENT_INSTALL.md`).

## IP (Surfshark static)

- Soft `px` can stay `none` if **every client PC runs Surfshark with the same static IP** before opening DAT in Laneora.  
- Same static on admin + clients ⇒ DAT owners see that US IP.  
- Optional later: Soft `set-proxy` if you get an HTTP proxy endpoint from Surfshark/another provider.
