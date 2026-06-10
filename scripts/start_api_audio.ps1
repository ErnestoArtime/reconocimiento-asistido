$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".\.venv311\Scripts\python.exe")) {
    throw "No existe .venv311. Ejecuta primero la preparacion de audio WhisperX."
}

& ".\.venv311\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
