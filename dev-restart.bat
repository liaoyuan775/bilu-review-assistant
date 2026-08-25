@echo off
chcp 65001 >nul
title Bilu Dev Server

echo ========================================
echo   Bilu 开发服务器 — 一键重启
echo ========================================
echo.

REM ── 配置 ──────────────────────────────────
set BACKEND_PORT=8789
set FRONTEND_PORT=4173
set BACKEND_DIR=D:\AgentLearning\bilu\backend
set FRONTEND_DIR=D:\AgentLearning\bilu\frontend

REM ── 杀旧进程 ──────────────────────────────
echo [1/3] 清理旧进程...

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr LISTENING') do (
    echo   杀掉后端 PID: %%p
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr LISTENING') do (
    echo   杀掉前端 PID: %%p
    taskkill /F /PID %%p >nul 2>&1
)
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo   清理完成
echo.

REM ── 启后端（带 --reload 热重载）─────────
echo [2/3] 启动后端 (port %BACKEND_PORT%)...
cd /d "%BACKEND_DIR%"
start "Bilu Backend" python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload
timeout /t 3 /nobreak >nul

REM ── 启前端 ────────────────────────────────
echo [3/3] 启动前端 (port %FRONTEND_PORT%)...
cd /d "%FRONTEND_DIR%"
start "Bilu Frontend" npx vite --host 127.0.0.1 --port %FRONTEND_PORT%

timeout /t 2 /nobreak >nul
echo.
echo ========================================
echo   后端: http://127.0.0.1:%BACKEND_PORT%/api/v1/health
echo   前端: http://127.0.0.1:%FRONTEND_PORT%
echo ========================================
echo.
pause
