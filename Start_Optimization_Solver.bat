@echo off
title Optimization Solver
cd /d "c:\Users\jinnie.ong\OneDrive - Nanyang Technological University\NTU DATA\NTU Works\Antigravity_Folder\BT2404"
echo ========================================================
echo   Optimization Solver - University Examination Server
echo ========================================================
echo Checking if server is already running...
curl.exe -s --max-time 1 http://localhost:8080/healthz | findstr /i "ok" >nul
if %errorlevel% equ 0 (
    echo ========================================================
    echo   Optimization Solver is ALREADY active and healthy!
    echo ========================================================
    echo.
    echo Launching browser at http://localhost:8080/ ...
    start "" "http://localhost:8080/"
    echo.
    echo The server is running and ready to accept formulations.
    echo You can keep this window or press any key to close it.
    pause >nul
    exit /b 0
)

set "PY_EXE=C:\Users\jinnie.ong\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

echo Starting dual-stack server on http://localhost:8080 ...
echo.
echo Launching browser at http://localhost:8080/ ...
start "" "http://localhost:8080/"

echo.
echo Server active on http://localhost:8080/ and http://127.0.0.1:8080/
echo Press Ctrl+C in this window to stop the server.
echo ========================================================
"%PY_EXE%" run_server.py
pause
