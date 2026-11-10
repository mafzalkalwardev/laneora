# Laneora client install (what you give end users)

## Package to send the client

1. **`dist\Laneora.exe`** — built with `build.ps1`  
2. Optional shortcut that sets Soft URL (recommended)

### Build the EXE (on your machine)

```powershell
cd "d:\Dispatch Softwares\Laneora"
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Output: `dist\Laneora.exe`

### Client shortcut (edit Soft URL first)

Create `Laneora Soft.bat` next to the EXE:

```bat
@echo off
REM <<< CHANGE THIS to your Soft shim address >>>
set LANEORA_SERVER_URL=http://YOUR_SERVER_IP:8787
set LANEORA_SKIP_UPDATE=1
start "" "%~dp0Laneora.exe"
```

Zip and send: `Laneora.exe` + `Laneora Soft.bat`

## What the client does

1. Install / enable **Surfshark** with **your static US IP** (same as admin)  
2. Run `Laneora Soft.bat` (or EXE after setting Soft URL)  
3. Soft login you created in the admin dashboard (username and password you set there)  
4. Open the module your admin turned on. **DAT Search** is one screen. **Dual DAT Search**, **3 DAT Search**, and **6 DAT Search** open that many search tabs. You only see the ones that were checked for your login.

## What you create for each client

```powershell
python scripts\soft_admin.py add-user theirUser theirPass
```

Tell them: Soft username + password + Soft server URL (in the bat file).

## Notes

- Soft **single-screen** is on: same Soft user on a second PC kicks the first.  
- DAT session is refreshed by **you** (`capture` + `push-capture`), not by the client.  
- Client does **not** need Chrome DAT login.
