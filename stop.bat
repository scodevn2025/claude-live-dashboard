@echo off
REM Stop claude-live-dashboard: kill uvicorn + cloudflared

echo [*] Stopping cloudflared tunnel...
taskkill /F /IM cloudflared.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  echo [-] cloudflared killed
) else (
  echo [=] cloudflared not running
)

echo [*] Stopping uvicorn backend...
REM Find process listening on :8765 → PID → kill
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
  echo [-] uvicorn PID %%a killed
)

echo.
echo [OK] Dashboard stopped.
timeout /t 2 /nobreak >nul
