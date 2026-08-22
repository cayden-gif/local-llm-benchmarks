@echo off
title Benchmarking local AI models
cd /d "%~dp0"

echo ============================================================
echo   Benchmarking every local model on this machine.
echo.
echo   This takes a few hours and the laptop will be slow while
echo   it runs. Results are saved after EVERY model, so closing
echo   this window loses nothing - just run it again to continue.
echo ============================================================
echo.

"C:\Users\RNGAI\jarvis_env\Scripts\python.exe" "%~dp0bench.py"

echo.
echo   Done. Results are in results.json
echo.
pause
