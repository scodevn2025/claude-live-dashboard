@echo off
REM Launcher claude-live-dashboard — ba double-click là chạy
REM 1. Kick uvicorn daemon ở background
REM 2. Mở trình duyệt mặc định

cd /d "%~dp0"

echo [*] Starting dashboard daemon on http://127.0.0.1:8765...
start "claude-live-dashboard" /B cmd /c "uv run python -X utf8 -m uvicorn src.main:app --host 127.0.0.1 --port 8765 --log-level warning"

echo [*] Waiting for server ready...
timeout /t 3 /nobreak >nul

echo [*] Opening browser...
start "" "http://127.0.0.1:8765/dashboard"

echo.
echo [+] Dashboard running. Keep this window open.
echo [+] Press Ctrl+C or close this window to stop daemon.
echo.
pause >nul
