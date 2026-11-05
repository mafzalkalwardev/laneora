@echo off
title Laneora
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  ".venv\Scripts\python.exe" scripts\make_brand.py
)

REM Local Soft shim (Start Soft Server.bat must be running).
set LANEORA_SERVER_URL=http://127.0.0.1:8787
set LANEORA_SOFT_FALLBACK_URL=http://127.0.0.1:8787
set LANEORA_SOFT_FALLBACK=1
set LANEORA_SKIP_UPDATE=1

".venv\Scripts\python.exe" -m app
