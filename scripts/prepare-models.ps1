# prepare-models.ps1 - AEGIS Model Inspector & Optional Pull Script
# Checks local Ollama daemon for installed models and offers user-confirmed model downloads.

$ErrorActionPreference = "Continue"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "    AEGIS MODEL RUNTIME PREPARATION      " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$ollamaUrl = "http://localhost:11434/api/tags"

Write-Host "Checking local Ollama daemon at $ollamaUrl..." -ForegroundColor Cyan

try {
    $res = Invoke-RestMethod -Uri $ollamaUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    $installedModels = $res.models | ForEach-Object { $_.name }
    
    Write-Host ""
    Write-Host "Installed Local Models in Ollama:" -ForegroundColor Green
    if ($installedModels) {
        foreach ($m in $installedModels) {
            Write-Host "  - $m" -ForegroundColor Green
        }
    } else {
        Write-Host "  (No models installed yet)" -ForegroundColor Yellow
    }
    
    Write-Host ""
    $requiredModel = "gemma3:4b"
    if ($installedModels -contains $requiredModel) {
        Write-Host "[PASS] Primary AEGIS model '$requiredModel' is INSTALLED and READY." -ForegroundColor Green
    } else {
        Write-Host "[WARN] Primary AEGIS model '$requiredModel' is NOT INSTALLED." -ForegroundColor Yellow
        $response = Read-Host "Would you like to pull '$requiredModel' now using 'ollama pull $requiredModel'? (y/N)"
        if ($response -eq "y" -or $response -eq "Y") {
            Write-Host "Running: ollama pull $requiredModel..." -ForegroundColor Cyan
            & ollama pull $requiredModel
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[PASS] Model '$requiredModel' pulled successfully." -ForegroundColor Green
            } else {
                Write-Host "[FAIL] Failed to pull model '$requiredModel'." -ForegroundColor Red
            }
        } else {
            Write-Host "Skipped model pull. Backend will run with degraded/simulated model fallback." -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "[ERROR] Could not connect to local Ollama daemon at $ollamaUrl" -ForegroundColor Red
    Write-Host "Please ensure Ollama is installed and running:" -ForegroundColor Yellow
    Write-Host "  1. Download Ollama from https://ollama.com" -ForegroundColor Yellow
    Write-Host "  2. Start the Ollama application" -ForegroundColor Yellow
    Write-Host "  3. Re-run 'powershell .\scripts\prepare-models.ps1'" -ForegroundColor Yellow
}
