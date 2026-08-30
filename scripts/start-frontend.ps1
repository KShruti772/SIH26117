# start-frontend.ps1 - Launcher for AEGIS Next.js Frontend Service

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendDir = Join-Path $projectRoot "frontend"
Set-Location $frontendDir

$nodeModules = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $nodeModules)) {
    Write-Host "[ERROR] Frontend node_modules not found at $nodeModules" -ForegroundColor Red
    Write-Host "Please run setup script first: powershell .\scripts\setup.ps1" -ForegroundColor Yellow
    Exit 1
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "    LAUNCHING AEGIS FRONTEND SERVICE     " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Frontend Path : $frontendDir" -ForegroundColor Yellow
Write-Host "URL           : http://localhost:3000" -ForegroundColor Green
Write-Host "-----------------------------------------"

npm run dev
