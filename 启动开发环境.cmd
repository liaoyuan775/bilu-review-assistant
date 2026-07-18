@echo off
chcp 65001 >nul
title Bilu Review Assistant - Development Logs
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-development.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Review the error above.
  pause
)
