# Laneora admin operations (you)

## Dashboard access

The admin page and a Soft client are different logins. A client whose username is `admin` cannot open the dashboard.

The server never writes a default dashboard password. On a new install:

```powershell
python scripts\soft_admin.py dashboard-set --generate-username --generate-password
```

The command prints the new username and password once. It stores a slow hash and a separate session signing key in `data\soft_config.json` (owner-read/write only). Put the password in a password manager. It is not written to the file.

Useful commands, from the server itself:

```powershell
python scripts\soft_admin.py migrate
python scripts\soft_admin.py sessions-revoke
python scripts\soft_admin.py dashboard-set --username NEWNAME
python scripts\soft_admin.py import-roster
python scripts\soft_admin.py import-roster --yes
python scripts\soft_admin.py roster-strip
python scripts\soft_admin.py totp-enroll
python scripts\soft_admin.py totp-disable
```

`dashboard-set` reads the password from `LANEORA_DASHBOARD_PASSWORD` or a hidden prompt. It does not take the password as an argument. It signs out every dashboard browser. Two-factor authentication is optional: password login keeps working until you confirm a code. Recovery codes are printed once at enrollment.

`migrate` hashes plaintext dashboard and client passwords already in `data\soft_config.json` and `data\local_users.json`. It does not print those passwords. Run it once before relying on a restarted server, or just start the server — startup migrates too. Copy those two files to a root-only folder before the first new start if you want a rollback. The previous release cannot check the hashes.

Accounts that exist only in `data\users.json` (the desktop roster) are not turned into server logins automatically. `import-roster` prints those usernames. Use `--yes` only for real dispatchers. On the VPS, after clients still sign in, `roster-strip` blanks roster passwords so that file is not a second copy of the secrets. Do not run `roster-strip` on a PC whose Laneora window refills passwords from that file.

Dispatcher apps already in the field keep calling `GET /authenticate`. That still works. New builds of this repo POST the password in the body, and fall back to GET only when an older server returns 404 or 405. After every dispatcher is on a build that POSTs, set `LANEORA_ALLOW_GET_AUTH=0` and restart. Leave it at the default until then.

Nginx in front of the app should keep sending `X-Forwarded-Proto` and the original `Host`. The app sets `Secure` on admin cookies when that proxy is on loopback and the request is HTTPS. Bind the process to `127.0.0.1` on the VPS (`LANEORA_SOFT_HOST=127.0.0.1`) so the port is not reachable except through nginx.

A restart drops the in-memory single-screen heartbeat. An open Laneora window retries a failed check and can continue without a new login if it is the next check in after the process is back and nobody else signs in as that user during the gap. It is a short blip, not a guaranteed quiet restart.

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
| **Every 12 hours** | Run `python scripts\soft_admin.py capture-if-expired`. It prints expiry only. Exit 0 means auth0 is still valid and Chrome stays untouched. Exit 2 means it is missing or expired: then run the capture below against the Chrome that is already signed in. |
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
