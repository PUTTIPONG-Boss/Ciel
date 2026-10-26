# Start Ciel on Windows:  .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    Write-Host "First run: creating virtual environment..."
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt

if (-not (Test-Path .env)) { Copy-Item .env.example .env }

& .\.venv\Scripts\python.exe -m ciel
