@echo off
REM Laneora client launcher. Edit the server address for this PC.
REM <<< CHANGE THIS to your Soft shim address >>>
set LANEORA_SERVER_URL=http://YOUR_SERVER_IP:8787
set LANEORA_SKIP_UPDATE=1
start "" "%~dp0Laneora.exe"
