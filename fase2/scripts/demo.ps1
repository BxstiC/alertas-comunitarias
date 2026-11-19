# Demo de 2 minutos para la presentacion (lo llama DEMO.bat o iniciar.ps1):
# escritura, lectura, cabeceras X-Instance / X-DB, balanceo, API key y limite de peticiones.
. "$PSScriptRoot\comun.ps1"

$Url = 'http://localhost:8000'
$cuerpo = Join-Path $env:TEMP 'aviso-demo.json'

function Titulo([string]$t) { Write-Host ''; Write-Host "--- $t" -ForegroundColor Cyan }

# Hace una peticion y devuelve codigo, cabeceras utiles y cuerpo.
function Pedir([string]$Metodo, [string]$Ruta, [switch]$SinKey) {
    $args_ = @('-s', '-i', '-m', '5', '-X', $Metodo)
    if (-not $SinKey) { $args_ += @('-H', "X-API-Key: $ApiKey") }
    if ($Metodo -eq 'POST') { $args_ += @('-H', 'Content-Type: application/json', '--data-binary', "@$cuerpo") }
    $salida = curl.exe @args_ "$Url$Ruta"
    $r = [ordered]@{ http = ''; instance = ''; db = ''; replica = ''; body = '' }
    foreach ($l in $salida) {
        if ($l -match '^HTTP/\S+\s+(\d{3})') { $r.http = $Matches[1] }
        elseif ($l -match '^X-Instance:\s*(\S+)') { $r.instance = $Matches[1] }
        elseif ($l -match '^X-DB:\s*(\S+)') { $r.db = $Matches[1] }
        elseif ($l -match '^X-Replica-Estado:\s*(\S+)') { $r.replica = $Matches[1] }
        elseif ($l -match '^\s*[\{\[]') { $r.body = $l }
    }
    return [pscustomobject]$r
}

function Mostrar($r) {
    $color = if ($r.http -match '^2') { 'Green' } else { 'Yellow' }
    Write-Host ("HTTP {0}   X-Instance: {1}   X-DB: {2}" -f $r.http, $r.instance, $r.db) -ForegroundColor $color -NoNewline
    if ($r.replica) { Write-Host "   X-Replica-Estado: $($r.replica)" } else { Write-Host '' }
}

Titulo '1. Escritura (POST) -> debe ir a la PRIMARIA'
$hora = (Get-Date).ToString('HH:mm:ss')
[IO.File]::WriteAllText($cuerpo, '{"titulo":"Corte de agua ' + $hora + '","descripcion":"Sin agua de 09:00 a 14:00 en calle Los Aromos","categoria":"corte_servicio"}')
$post = Pedir 'POST' '/api/v1/avisos'
Mostrar $post
$id = ''
if ($post.body) { $id = ($post.body | ConvertFrom-Json).id; Write-Host "Aviso creado con id $id" }

Titulo '2. Lectura de la lista (GET) -> debe venir de la REPLICA'
$get = Pedir 'GET' '/api/v1/avisos?limit=3'
Mostrar $get
if ($get.body) {
    $lista = $get.body | ConvertFrom-Json
    Write-Host "Avisos vigentes: $($lista.total). Ultimos:"
    $lista.items | ForEach-Object { Write-Host ("  #{0}  [{1}]  {2}" -f $_.id, $_.categoria, $_.titulo) }
}

if ($id) {
    Titulo "3. Lectura del aviso recien escrito (GET /api/v1/avisos/$id)"
    Mostrar (Pedir 'GET' "/api/v1/avisos/$id")
}

Titulo '4. Balanceo: X-Instance alterna entre app-1 y app-2'
1..6 | ForEach-Object { Mostrar (Pedir 'GET' '/api/v1/avisos?limit=1') }

Titulo '5. Gateway - API key: sin clave se rechaza'
Mostrar (Pedir 'GET' '/api/v1/avisos' -SinKey)

Titulo '6. Gateway - limite de peticiones: 30 seguidas (limite 10/s, rafaga 20)'
$codigos = 1..30 | ForEach-Object { curl.exe -s -o NUL -m 5 -w '%{http_code}' -H "X-API-Key: $ApiKey" "$Url/api/v1/avisos?limit=1" }
$codigos | Group-Object | Sort-Object Name | ForEach-Object { Write-Host ("  HTTP {0}: {1} veces" -f $_.Name, $_.Count) }

Remove-Item $cuerpo -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'Demo terminada.' -ForegroundColor Green
