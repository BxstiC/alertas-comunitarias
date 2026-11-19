# Prueba de falla 2: corta (o restaura) SOLO la comunicacion primaria -> replica.
# La replica sigue en la red "data", asi que las apps la pueden seguir leyendo,
# pero deja de recibir WAL: sus datos quedan desactualizados.
#
# Uso (desde la carpeta fase2):
#   powershell -ExecutionPolicy Bypass -File scripts\replicacion.ps1 -Accion cortar
#   powershell -ExecutionPolicy Bypass -File scripts\replicacion.ps1 -Accion restaurar
#   powershell -ExecutionPolicy Bypass -File scripts\replicacion.ps1 -Accion estado
param([ValidateSet('cortar', 'restaurar', 'estado')][string]$Accion = 'estado')
. "$PSScriptRoot\comun.ps1"

$proyecto = (docker compose config --format json | ConvertFrom-Json).name
$red = "${proyecto}_replicacion"
$contenedor = (docker compose ps -q db-replica)

switch ($Accion) {
    'cortar'    { docker network disconnect $red $contenedor; Write-Host "$(Hora)  Replicacion cortada (db-replica fuera de $red)" }
    'restaurar' { docker network connect $red $contenedor;    Write-Host "$(Hora)  Replicacion restaurada (db-replica de vuelta en $red)" }
}

Write-Host "$(Hora)  Estado:"
Write-Host ("  primaria: ultimo id = {0}; replicas conectadas = {1}" -f `
    (Sql (Servicio-Primaria) 'SELECT max(id) FROM avisos'), (Sql (Servicio-Primaria) 'SELECT count(*) FROM pg_stat_replication'))
Write-Host ("  replica : ultimo id = {0}; walreceiver = {1}" -f `
    (Sql 'db-replica' 'SELECT max(id) FROM avisos'), (Sql 'db-replica' "SELECT coalesce((SELECT status FROM pg_stat_wal_receiver), 'sin conexion')"))
