$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    $python = "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
}

if (-not (Test-Path $python) -and $python -ne "python") {
    throw "No se encontro Python. Instala Python 3.11+ y marca Add python.exe to PATH."
}

if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --default-timeout 180 -r requirements.txt
& ".\.venv\Scripts\python.exe" scripts\smoke_test.py

