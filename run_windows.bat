@echo off
cd /d %~dp0
start "KV Kontroll Server" cmd /k python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
choice /T 3 /D Y >nul
start "" http://127.0.0.1:8000
