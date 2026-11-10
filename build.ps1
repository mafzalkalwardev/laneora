$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  py -3 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.\.venv\Scripts\python.exe scripts\make_brand.py

.\.venv\Scripts\pyinstaller.exe `
  --noconfirm `
  --onefile `
  --windowed `
  --name "Laneora" `
  --icon "app\resources\app.ico" `
  --add-data "app\resources\laneora.qss;app\resources" `
  --add-data "app\resources\logo.png;app\resources" `
  --add-data "app\resources\mark.png;app\resources" `
  --add-data "app\resources\app.ico;app\resources" `
  --hidden-import PyQt5.QtWebEngineWidgets `
  --hidden-import PyQt5.QtWebEngineCore `
  "app\main.py"

Write-Host "Built dist\Laneora.exe"
Write-Host "Give clients: dist\Laneora.exe + CLIENT_INSTALL.md shortcut bat"
Write-Host "Entry is app\main.py. Do not add a server import; the onefile exe then fails with No module named server."
