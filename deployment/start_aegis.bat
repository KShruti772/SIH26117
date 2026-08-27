@echo off
title AEGIS Private LAN Launcher
echo Initiating Aegis Startup Sequence...
powershell -ExecutionPolicy Bypass -File "%~dp0start_aegis.ps1"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Aegis failed to start.
    pause
)
