@echo off
chcp 65001 >nul
title EnREAD Launcher

cd /d "%~dp0"

REM Minimize current window (main.py window)
powershell -window minimized -command ""

REM Start UI window minimized
REM Debug mode: use "python" instead of "pythonw" to see UI errors
REM For production, change back to: start "EnREAD UI" /min pythonw floating_ui.py
start "EnREAD UI" /min cmd /c "python floating_ui.py || pause"

timeout /t 2 /nobreak >nul

python main.py

if errorlevel 1 (
    echo.
    echo [Error] main.py exited with code: %errorlevel%
    pause
)