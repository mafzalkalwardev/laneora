@echo off
title Refresh DAT cookies into Soft
cd /d "%~dp0\.."

echo.
echo 1) Surfshark static IP ON
echo 2) Chrome Profile 410 open on Search Loads (debugging port 9334)
echo.
pause

".venv\Scripts\python.exe" scripts\capture_dat_from_cdp.py 9334 datshare datshare123
if errorlevel 1 (
  echo Capture failed. Start Chrome with:
  echo   chrome.exe --remote-debugging-port=9334 --remote-allow-origins=* --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" --profile-directory="Profile 410" https://one.dat.com/search-loads
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\soft_admin.py push-capture
".venv\Scripts\python.exe" scripts\soft_admin.py multi-screen off
".venv\Scripts\python.exe" scripts\soft_admin.py status
echo.
echo Pushed to all Soft users. Clients should Reconnect or re-login.
pause
