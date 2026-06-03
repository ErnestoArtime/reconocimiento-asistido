$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "No existe .venv. Ejecuta primero: .\scripts\setup.ps1"
}

& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

