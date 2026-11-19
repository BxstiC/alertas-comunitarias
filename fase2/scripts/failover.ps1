# Prueba de falla 3: mata la primaria, promueve la replica y redirige las escrituras.
# Es una promocion MANUAL (no hay Patroni ni otro orquestador): cada paso queda con hora.
#
# Uso (desde la carpeta fase2):
#   powershell -ExecutionPolicy Bypass -File scripts\failover.ps1
# Para volver al estado inicial: scripts\restaurar.ps1 -Confirmar  (borra los datos)
. "$PSScriptRoot\comun.ps1"

if ((Servicio-Primaria) -ne 'db-primary') {
    Write-Host 'El failover ya se hizo (DB_PRIMARY_HOST apunta a la replica). Usa scripts\restaurar.ps1 primero.'
    exit 1
}

$inicio = Get-Date
Write-Host "$(Hora)  1. Matando la primaria (docker compose kill db-primary)"
docker compose kill db-primary | Out-Null

Write-Host "$(Hora)  2. Promoviendo la replica (pg_promote)"
$r = Sql 'db-replica' 'SELECT pg_promote(true, 30)'
Write-Host "             pg_promote -> $r ; en recuperacion -> $(Sql 'db-replica' 'SELECT pg_is_in_recovery()')"

Write-Host "$(Hora)  3. Las apps escriben ahora en db-replica (DB_PRIMARY_HOST=db-replica en .env)"
Escribir-Env 'DB_PRIMARY_HOST' 'db-replica'

# Se recrean de a una para que siempre quede una instancia atendiendo lecturas.
foreach ($app in @('app-1', 'app-2')) {
    Write-Host "$(Hora)     recreando $app"
    docker compose up -d --no-deps $app 2>$null | Out-Null
    do {
        Start-Sleep -Milliseconds 500
        docker compose exec -T $app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1)" 2>$null | Out-Null
    } while ($LASTEXITCODE -ne 0)
    Write-Host "$(Hora)     $app lista"
}

$total = ((Get-Date) - $inicio).TotalSeconds
Write-Host ("$(Hora)  Failover terminado en {0:N1} s (desde el kill hasta las dos apps listas)." -f $total)
Write-Host 'Ojo: db-primary NO se debe volver a levantar tal cual: seria una segunda primaria (split brain).'
