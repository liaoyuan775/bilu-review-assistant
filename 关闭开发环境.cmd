@echo off
chcp 65001 >nul
title Stop Bilu Review Assistant
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-development.ps1"
if errorlevel 1 (
  echo.
  echo Shutdown was incomplete. Review the error above.
)
pause
