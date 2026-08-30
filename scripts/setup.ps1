# setup.ps1 - AEGIS Environment Setup Script
# Automates local virtual environment creation, package installation, directory initialization, and DB setup.

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   AEGIS AUTOMATED ENVIRONMENT SETUP     " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

# 1. Initialize Configuration (.env) if missing
$envFile = Join-Path $projectRoot ".env"
$envExample = Join-Path $projectRoot ".env.example"

if (-not (Test-Path $envFile)) {
    Write-Host "[1/6] Initializing .env configuration from template..." -ForegroundColor Cyan
    Copy-Item $envExample $envFile
    Write-Host "      Created .env configuration file." -ForegroundColor Green
} else {
    Write-Host "[1/6] .env configuration file exists. Preserving existing settings." -ForegroundColor Green
}

# 2. Create Required Directory Infrastructure
Write-Host "[2/6] Verifying local directory infrastructure..." -ForegroundColor Cyan
$requiredDirs = @(
    "data/private",
    "data/knowledge_base",
    "vectorstore",
    "models",
    "outputs"
)

foreach ($dir in $requiredDirs) {
    $targetPath = Join-Path $projectRoot $dir
    if (-not (Test-Path $targetPath)) {
        New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
        Write-Host "      Created directory: $dir" -ForegroundColor Green
    } else {
        Write-Host "      Directory verified: $dir" -ForegroundColor Gray
    }
}

# 3. Python Virtual Environment Setup
Write-Host "[3/6] Setting up Python backend virtual environment..." -ForegroundColor Cyan
$venvPath = Join-Path $projectRoot "backend\.venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "      Creating Python virtual environment in backend/.venv..." -ForegroundColor Yellow
    python -m venv $venvPath
    Write-Host "      Virtual environment created successfully." -ForegroundColor Green
} else {
    Write-Host "      Virtual environment exists." -ForegroundColor Green
}

# 4. Install Backend Requirements
Write-Host "[4/6] Installing backend Python packages from requirements.txt..." -ForegroundColor Cyan
$reqFile = Join-Path $projectRoot "backend\requirements.txt"
& $venvPython -m pip install --upgrade pip | Out-Null
& $venvPython -m pip install -r $reqFile
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Backend packages installed successfully." -ForegroundColor Green
} else {
    Write-Host "      [ERROR] Backend package installation failed." -ForegroundColor Red
    Exit 1
}

# 5. Initialize Local Database Schema & Seed Demo Accounts
Write-Host "[5/6] Initializing local SQLite database schema and demo user accounts..." -ForegroundColor Cyan
$seedScript = Join-Path $projectRoot "scripts\seed-users.py"
& $venvPython $seedScript
if ($LASTEXITCODE -eq 0) {
    Write-Host "      SQLite database schema and demo accounts provisioned successfully." -ForegroundColor Green
} else {
    Write-Host "      [ERROR] Database initialization/seeding failed." -ForegroundColor Red
    Exit 1
}

# 6. Install Frontend Node Dependencies
Write-Host "[6/6] Checking frontend Node.js dependencies..." -ForegroundColor Cyan
$frontendDir = Join-Path $projectRoot "frontend"
Set-Location $frontendDir

if (-not (Test-Path "node_modules")) {
    Write-Host "      Installing frontend packages via npm install..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      Frontend dependencies installed successfully." -ForegroundColor Green
    } else {
        Write-Host "      [ERROR] Frontend package installation failed." -ForegroundColor Red
        Exit 1
    }
} else {
    Write-Host "      Frontend node_modules directory verified." -ForegroundColor Green
}

Set-Location $projectRoot

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   AEGIS SETUP COMPLETED SUCCESSFULLY    " -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run 'powershell .\scripts\check-environment.ps1' to verify health" -ForegroundColor Yellow
Write-Host "  2. Run 'powershell .\scripts\prepare-models.ps1' to check Ollama models" -ForegroundColor Yellow
Write-Host "  3. Launch backend using 'powershell .\scripts\start-backend.ps1'" -ForegroundColor Yellow
Write-Host "  4. Launch frontend using 'powershell .\scripts\start-frontend.ps1'" -ForegroundColor Yellow
