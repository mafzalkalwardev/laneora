@echo off
title Laneora
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  ".venv\Scripts\python.exe" scripts\make_brand.py
)

start "Laneora Local API" cmd /k ""%~dp0.venv\Scripts\python.exe" "%~dp0server\local_api.py""
timeout /t 2 /nobreak >nul
".venv\Scripts\python.exe" -m app
