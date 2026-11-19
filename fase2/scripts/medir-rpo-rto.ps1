# Calcula RPO y RTO a partir del CSV de scripts\escrituras.ps1.
#  - RPO: avisos que recibieron 201 (confirmados al cliente) y NO estan en la primaria actual.
#  - RTO: tiempo entre la ultima escritura correcta antes de la falla y la primera correcta despues.
#
# Uso (desde la carpeta fase2):
#   powershell -ExecutionPolicy Bypass -File scripts\medir-rpo-rto.ps1 -Csv escrituras.csv
param([string]$Csv = 'escrituras.csv')
. "$PSScriptRoot\comun.ps1"

$filas = @(Import-Csv $Csv)
$formato = 'yyyy-MM-ddTHH:mm:ss.fff'
$cultura = [Globalization.CultureInfo]::InvariantCulture
foreach ($f in $filas) { $f | Add-Member -NotePropertyName t -NotePropertyValue ([datetime]::ParseExact($f.ts, $formato, $cultura)) }

$ok = @($filas | Where-Object { $_.http -eq '201' })
Write-Host "Escrituras intentadas: $($filas.Count)"
$filas | Group-Object http | Sort-Object Name | ForEach-Object { Write-Host ("  HTTP {0}: {1}" -f $_.Name, $_.Count) }

# ---------- RTO ----------
$primerFallo = $null; $ultimoOk = $null; $recuperado = $null
for ($i = 0; $i -lt $filas.Count; $i++) {
    if (-not $primerFallo) {
        if ($filas[$i].http -eq '201') { $ultimoOk = $filas[$i] } elseif ($ultimoOk) { $primerFallo = $filas[$i] }
    } elseif ($filas[$i].http -eq '201') { $recuperado = $filas[$i]; break }
}
if (-not $primerFallo) {
    Write-Host 'RTO: no hubo escrituras fallidas en el CSV.'
} elseif (-not $recuperado) {
    Write-Host "RTO: las escrituras fallan desde $($primerFallo.ts) y no se recuperaron dentro del CSV."
} else {
    $rto = ($recuperado.t - $ultimoOk.t).TotalSeconds
    $fallidas = @($filas | Where-Object { $_.t -gt $ultimoOk.t -and $_.t -lt $recuperado.t }).Count
    Write-Host ''
    Write-Host "Ultima escritura OK antes de la falla : $($ultimoOk.ts)  (id $($ultimoOk.id))"
    Write-Host "Primera escritura fallida             : $($primerFallo.ts)  (HTTP $($primerFallo.http))"
    Write-Host "Primera escritura OK despues          : $($recuperado.ts)  (id $($recuperado.id))"
    Write-Host ("RTO medido: {0:N1} s sin poder escribir ({1} peticiones fallidas)" -f $rto, $fallidas)
}

# ---------- RPO ----------
$ids = @($ok | ForEach-Object { [int64]$_.id })
if ($ids.Count -eq 0) { Write-Host 'RPO: no hay escrituras confirmadas en el CSV.'; exit 0 }
$servicio = Servicio-Primaria
# Se compara id + titulo (el titulo lleva el numero de escritura n). Comparar solo por id
# no basta: tras el failover la nueva primaria puede REUTILIZAR ids que la primaria vieja
# ya habia confirmado (la secuencia de la replica quedo atrasada).
$presentes = @{}
Sql $servicio "SELECT id || '|' || titulo FROM avisos WHERE titulo LIKE 'Prueba de escritura %'" | ForEach-Object {
    if ($_.Trim()) { $presentes[$_.Trim()] = $true }
}
$perdidos = @($ok | Where-Object { -not $presentes.ContainsKey("$($_.id)|Prueba de escritura $($_.n)") })
$reutilizados = @($perdidos | Where-Object { $presentes.Keys -like "$($_.id)|*" })
Write-Host ''
Write-Host "Primaria consultada: $servicio. Escrituras confirmadas (201): $($ids.Count)"
if ($perdidos.Count -eq 0) {
    Write-Host 'RPO medido: 0 avisos perdidos (todo lo confirmado esta en la primaria actual).'
} else {
    $desde = $perdidos[0].ts; $hasta = $perdidos[-1].ts
    $ventana = ($perdidos[-1].t - $perdidos[0].t).TotalSeconds
    Write-Host ("RPO medido: {0} avisos confirmados se PERDIERON ({1} a {2}, ventana de {3:N1} s)" -f $perdidos.Count, $desde, $hasta, $ventana)
    Write-Host ("  ids perdidos: {0}" -f (($perdidos | ForEach-Object { $_.id }) -join ', '))
    if ($reutilizados.Count -gt 0) {
        Write-Host ("  OJO: {0} de esos ids ahora pertenecen a OTRO aviso en la nueva primaria: {1}" -f `
            $reutilizados.Count, (($reutilizados | ForEach-Object { $_.id }) -join ', '))
    }
}
