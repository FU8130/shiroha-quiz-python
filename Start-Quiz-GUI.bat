@echo off
rem Shiroha Quiz - GUI launcher (ASCII only, keep CRLF)
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY if exist "%~dp0runtime\python.exe" set "PY=%~dp0runtime\python.exe"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  echo Python not found. Install Python 3.10+ and try again.
  pause
  exit /b 1
)

%PY% -X utf8 -u quiz.py --web %*
if errorlevel 1 (
  echo.
  echo Quiz GUI exited with an error. Check the message above.
  pause
)
