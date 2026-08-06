@echo off
title OAS Launcher
set "_root=%~dp0"

echo [1/2] Starting OAS backend (server.py)...
start "OAS Backend" /D "%_root%" "%_root%.venv\Scripts\python.exe" server.py

timeout /t 8 /nobreak > nul

echo [2/2] Starting OASX...
start "" /D "%_root%..\OASX" "%_root%..\OASX\oasx.exe"

echo.
echo OAS backend: http://127.0.0.1:22267
echo OASX window should appear shortly.
