@echo off
title Alertas Vecinales - Detener
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fase2\scripts\detener.ps1"
echo.
pause
