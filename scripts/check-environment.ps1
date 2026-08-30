# check-environment.ps1 - AEGIS Environment & Service Health Diagnostic Script
# Performs real, non-simulated runtime checks across system dependencies.

$ErrorActionPreference = "Continue"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  AEGIS ENVIRONMENT DIAGNOSTIC SYSTEM    " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Write-Host "PROJECT ROOT: $projectRoot" -ForegroundColor Yellow

$overallReady = $true

# 1. Python Check
$pythonVersion = & python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] PYTHON              : Installed ($pythonVersion)" -ForegroundColor Green
} else {
    Write-Host "[FAIL] PYTHON              : NOT FOUND (Python 3.12+ required)" -ForegroundColor Red
    $overallReady = $false
}

# 2. Node.js Check
$nodeVersion = & node --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] NODE.JS             : Installed ($nodeVersion)" -ForegroundColor Green
} else {
    Write-Host "[FAIL] NODE.JS             : NOT FOUND (Node.js v20+ required)" -ForegroundColor Red
    $overallReady = $false
}

# 3. NPM Check
$npmVersion = & npm --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] NPM                 : Installed ($npmVersion)" -ForegroundColor Green
} else {
    Write-Host "[FAIL] NPM                 : NOT FOUND" -ForegroundColor Red
    $overallReady = $false
}

# 4. Backend Virtual Environment Check
$venvPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "[PASS] BACKEND VENV        : Present ($venvPython)" -ForegroundColor Green
} else {
    Write-Host "[WARN] BACKEND VENV        : NOT CREATED (Run scripts/setup.ps1)" -ForegroundColor Yellow
    $overallReady = $false
}

# 5. Frontend Node Modules Check
$nodeModules = Join-Path $projectRoot "frontend\node_modules"
if (Test-Path $nodeModules) {
    Write-Host "[PASS] FRONTEND DEPS       : Installed ($nodeModules)" -ForegroundColor Green
} else {
    Write-Host "[WARN] FRONTEND DEPS       : NOT INSTALLED (Run scripts/setup.ps1)" -ForegroundColor Yellow
    $overallReady = $false
}

# 6. Environment File Check
$envFile = Join-Path $projectRoot ".env"
if (Test-Path $envFile) {
    Write-Host "[PASS] ENV CONFIG          : Present (.env)" -ForegroundColor Green
} else {
    Write-Host "[WARN] ENV CONFIG          : MISSING (.env file not created)" -ForegroundColor Yellow
    $overallReady = $false
}

# 7. SQLite Database Check
$dbPath = Join-Path $projectRoot "data\private\aegis_auth.db"
if (Test-Path $dbPath) {
    Write-Host "[PASS] SQLITE DATABASE     : Present ($dbPath)" -ForegroundColor Green
} else {
    Write-Host "[WARN] SQLITE DATABASE     : NOT INITIALIZED (Run scripts/setup.ps1)" -ForegroundColor Yellow
}

# 8. ChromaDB Vectorstore Directory Check
$vectorPath = Join-Path $projectRoot "vectorstore"
if (Test-Path $vectorPath) {
    Write-Host "[PASS] CHROMADB VECTORSTORE: Present ($vectorPath)" -ForegroundColor Green
} else {
    Write-Host "[WARN] CHROMADB VECTORSTORE: UNINITIALIZED (Will auto-create on document upload)" -ForegroundColor Yellow
}

# 9. Ollama Daemon Connectivity Check
$ollamaUrl = "http://localhost:11434/api/tags"
$ollamaOnline = $false
try {
    $res = Invoke-RestMethod -Uri $ollamaUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    Write-Host "[PASS] OLLAMA DAEMON       : ONLINE ($ollamaUrl)" -ForegroundColor Green
    $ollamaOnline = $true
    
    # 10. Ollama Models Check
    $installedModels = $res.models | ForEach-Object { $_.name }
    if ($installedModels -contains "gemma3:4b") {
        Write-Host "[PASS] MODEL gemma3:4b     : INSTALLED" -ForegroundColor Green
    } else {
        Write-Host "[WARN] MODEL gemma3:4b     : NOT INSTALLED (Run scripts/prepare-models.ps1)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] OLLAMA DAEMON       : OFFLINE OR UNREACHABLE ($ollamaUrl)" -ForegroundColor Yellow
    Write-Host "       (Inference will run in degraded/mock mode until Ollama daemon is started)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "-----------------------------------------" -ForegroundColor Cyan
if ($overallReady) {
    Write-Host "OVERALL ENVIRONMENT STATUS : READY" -ForegroundColor Green
} else {
    Write-Host "OVERALL ENVIRONMENT STATUS : REQUIRES SETUP (Run scripts/setup.ps1)" -ForegroundColor Yellow
}
Write-Host "-----------------------------------------" -ForegroundColor Cyan
