# start-backend.ps1 - Launcher for AEGIS FastAPI Backend Service

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Local virtual environment python not found at $venvPython" -ForegroundColor Red
    Write-Host "Please run setup script first: powershell .\scripts\setup.ps1" -ForegroundColor Yellow
    Exit 1
}

# Ensure .env file exists
$envFile = Join-Path $projectRoot ".env"
$envExample = Join-Path $projectRoot ".env.example"
if (-not (Test-Path $envFile)) {
    Write-Host "[WARN] .env missing. Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item $envExample $envFile
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "     LAUNCHING AEGIS BACKEND DAEMON      " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Root Path : $projectRoot" -ForegroundColor Yellow
Write-Host "Python    : $venvPython" -ForegroundColor Yellow
Write-Host "Endpoint  : http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "-----------------------------------------"

& $venvPython -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
