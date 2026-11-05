@echo off
title Laneora Soft Server
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

set LANEORA_SOFT_HOST=0.0.0.0
set LANEORA_SOFT_PORT=8787
echo Soft shim listening on http://0.0.0.0:8787
echo Clients use: http://YOUR_LAN_IP:8787
echo Admin docs: ADMIN_OPS.md
".venv\Scripts\python.exe" server\soft_shim.py
pause
