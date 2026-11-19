@echo off
title Alertas Vecinales - Reiniciar desde cero
echo ATENCION: esto BORRA todos los datos de la base (primaria y replica)
echo y vuelve a levantar el sistema desde cero.
echo.
set /p RESP=Escribe SI para continuar:
if /i not "%RESP%"=="SI" (
    echo Cancelado.
    pause
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fase2\scripts\iniciar.ps1" -DesdeCero
echo.
pause
