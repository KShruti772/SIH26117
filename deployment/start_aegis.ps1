# start_aegis.ps1 - AEGIS private LAN deployment startup script
# Enforces air-gapped sovereign execution limits

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "      AEGIS SOVEREIGN AI WORKBENCH       " -ForegroundColor Cyan
Write-Host "        Private LAN Startup Daemon       " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Verify workspace environment
$venvPath = Join-Path $PSScriptRoot "..\backend\.venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Local virtual environment python not found at $venvPython" -ForegroundColor Red
    Write-Host "Please run the setup commands first:" -ForegroundColor Yellow
    Write-Host "   python -m venv backend/.venv"
    Write-Host "   backend\.venv\Scripts\python -m pip install -r backend\requirements.txt"
    Exit 1
}

# 2. Check configuration file
$envExample = Join-Path $PSScriptRoot "..\.env.example"
$envFile = Join-Path $PSScriptRoot "..\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "[WARN] .env configuration file is missing. Initializing from .env.example..." -ForegroundColor Yellow
    Copy-Item $envExample $envFile
}

# 3. Detect LAN IP addresses on the machine
Write-Host ""
Write-Host "[INFO] Scanning active network adapters for private LAN IP addresses..." -ForegroundColor Cyan
$adapters = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { 
    $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" 
}

if ($adapters) {
    Write-Host "Detected LAN IP Addresses:" -ForegroundColor Green
    foreach ($adapter in $adapters) {
        Write-Host "  - Interface: $($adapter.InterfaceAlias) | IP: $($adapter.IPAddress)" -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] No active private LAN adapters detected. Access will be restricted to localhost." -ForegroundColor Yellow
}

# 4. Extract current settings from .env
$hostSetting = "127.0.0.1"
$portSetting = "8000"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^HOST=(.+)$") { $hostSetting = $Matches[1].Trim() }
        if ($_ -match "^PORT=(.+)$") { $portSetting = $Matches[1].Trim() }
    }
}

Write-Host ""
Write-Host "Current Configuration settings:" -ForegroundColor Cyan
Write-Host "  HOST: $hostSetting" -ForegroundColor Yellow
Write-Host "  PORT: $portSetting" -ForegroundColor Yellow

if ($hostSetting -eq "127.0.0.1") {
    Write-Host "[IMPORTANT] HOST is currently set to 127.0.0.1 (localhost only)." -ForegroundColor Cyan
    Write-Host "To make AEGIS accessible to other machines on your private LAN, set HOST=0.0.0.0 in .env." -ForegroundColor Cyan
} else {
    Write-Host "[INFO] Server is configured to bind to $hostSetting, listening for LAN traffic." -ForegroundColor Green
}

# 5. Launch FastAPI backend
Write-Host ""
Write-Host "Launching AEGIS Backend Daemon..." -ForegroundColor Green
Write-Host "Press Ctrl+C to terminate the daemon server." -ForegroundColor Yellow
Write-Host "-----------------------------------------"

Set-Location (Join-Path $PSScriptRoot "..")
Start-Process -FilePath $venvPython -ArgumentList "backend\app\main.py" -NoNewWindow -Wait
