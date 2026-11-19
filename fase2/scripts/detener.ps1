# Detiene todos los contenedores SIN borrar datos (lo llama DETENER.bat).
. "$PSScriptRoot\comun.ps1"
docker compose stop
Write-Host ''
Write-Host 'Sistema detenido. Los datos se conservan. Para volver a levantarlo: INICIAR.bat' -ForegroundColor Green
