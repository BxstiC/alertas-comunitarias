# Vuelve al estado inicial despues de las pruebas de falla: quita DB_PRIMARY_HOST de .env,
# BORRA los volumenes (primaria y replica) y levanta todo desde cero.
#
# Uso (desde la carpeta fase2):
#   powershell -ExecutionPolicy Bypass -File scripts\restaurar.ps1 -Confirmar
param([switch]$Confirmar)
. "$PSScriptRoot\comun.ps1"

if (-not $Confirmar) {
    Write-Host 'Este script BORRA todos los datos de la base. Ejecutalo con -Confirmar.'
    exit 1
}
if (Test-Path (Join-Path $Raiz '.env')) { Escribir-Env 'DB_PRIMARY_HOST' '' }
docker compose down -v
docker compose up -d --build
docker compose ps
