@echo off
cd /d "%~dp0"
echo Starting MathVox API on http://127.0.0.1:8080
echo Keep this window open. Press Ctrl+C to stop.
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080
pause
