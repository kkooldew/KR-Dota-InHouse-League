@echo off
rem Double-click to start the inhouse bot. Close this window to stop it.
title Dota Inhouse Bot
cd /d "%~dp0"
python bot.py
echo.
pause
