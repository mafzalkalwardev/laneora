@echo off
title Chrome DAT (capture mode)
echo.
echo This reopens YOUR logged-in Chrome profile (Profile 1 / Search Loads)
echo with debugging so Laneora can read cookies from THAT same Chrome.
echo Do not use a different profile.
echo.
echo Steps:
echo   1) Close ALL Chrome windows first (all profiles).
echo   2) Press any key here.
echo   3) Log into DAT until Search Loads is visible (same account as before).
echo   4) Tell the agent: recapture   (agent will NOT kill Chrome)
echo.
pause

taskkill /IM chrome.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9334 ^
  --remote-allow-origins=* ^
  --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" ^
  --profile-directory="Profile 1" ^
  "https://one.dat.com/search-loads"

echo.
echo Chrome started with CDP on port 9334. Log into DAT now (Search Loads).
echo Then tell the agent: recapture
pause
