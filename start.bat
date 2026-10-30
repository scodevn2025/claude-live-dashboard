@echo off
REM Launcher claude-live-dashboard — ba double-click là chạy
REM 1. Start uvicorn backend 127.0.0.1:8765 (nếu chưa chạy)
REM 2. Start cloudflared tunnel → dashboard.scodevn.tech (nếu chưa chạy)
REM 3. Mở browser URL public (fallback local nếu tunnel down)

cd /d "%~dp0"
chcp 65001 >nul

echo.
echo === Claude Live Dashboard launcher ===
echo.

REM --- Backend check ---
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8765/api/health > "%TEMP%\cld_health.txt" 2>nul
set /p HEALTH=<"%TEMP%\cld_health.txt"
del "%TEMP%\cld_health.txt" >nul 2>&1

if "%HEALTH%"=="200" (
  echo [=] Backend already running on :8765
) else (
  REM Load .env if exists (DASHBOARD_USER + DASHBOARD_PASSWORD cho basic auth)
  if exist .env (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
    echo [+] Loaded .env credentials
  ) else (
    echo [!] WARNING: .env missing — backend chạy NO AUTH mode
  )
  echo [+] Starting uvicorn backend on :8765...
  start "claude-live-dashboard · backend" /min cmd /c "uv run python -X utf8 -m uvicorn src.main:app --host 127.0.0.1 --port 8765 --log-level warning"
  timeout /t 3 /nobreak >nul
)

REM --- Tunnel check (process name) ---
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /i "cloudflared.exe" >nul
if %ERRORLEVEL% EQU 0 (
  echo [=] Cloudflared tunnel already running
) else (
  echo [+] Starting cloudflared tunnel claude-dashboard...
  start "claude-live-dashboard · tunnel" /min cmd /c "bin\cloudflared.exe tunnel run claude-dashboard"
  timeout /t 4 /nobreak >nul
)

echo.
echo [OK] Dashboard URLs:
echo      Public:  https://dashboard.scodevn.tech/dashboard
echo      Local:   http://127.0.0.1:8765/dashboard
echo.
echo [*] Opening browser (public URL)...
start "" "https://dashboard.scodevn.tech/dashboard"

echo.
echo [+] Backend + tunnel chạy nền (minimized trong taskbar).
echo [+] Đóng cửa sổ này không stop. Dùng stop.bat hoặc kill process.
echo.
timeout /t 2 /nobreak >nul
