# Demo de 2 minutos para la presentacion (lo llama DEMO.bat o iniciar.ps1):
# escritura, lectura, cabeceras X-Instance / X-DB, balanceo, API key y limite de peticiones.
. "$PSScriptRoot\comun.ps1"

$Url = 'http://localhost:8000'
$cuerpo = Join-Path $env:TEMP 'aviso-demo.json'

function Titulo([string]$t) { Write-Host ''; Write-Host "--- $t" -ForegroundColor Cyan }

# Hace una peticion y devuelve codigo, cabeceras utiles y cuerpo.
function Pedir([string]$Metodo, [string]$Ruta, [switch]$SinKey, [string]$Key = $ApiKey) {
    $args_ = @('-s', '-i', '-m', '5', '-X', $Metodo)
    if (-not $SinKey) { $args_ += @('-H', "X-API-Key: $Key") }
    if ($Metodo -eq 'POST') { $args_ += @('-H', 'Content-Type: application/json', '--data-binary', "@$cuerpo") }
    $salida = curl.exe @args_ "$Url$Ruta"
    $r = [ordered]@{ http = ''; cliente = ''; instance = ''; db = ''; replica = ''; body = '' }
    foreach ($l in $salida) {
        if ($l -match '^HTTP/\S+\s+(\d{3})') { $r.http = $Matches[1] }
        elseif ($l -match '^X-Instance:\s*(\S+)') { $r.instance = $Matches[1] }
        elseif ($l -match '^X-Cliente:\s*(\S+)') { $r.cliente = $Matches[1] }
        elseif ($l -match '^X-DB:\s*(\S+)') { $r.db = $Matches[1] }
        elseif ($l -match '^X-Replica-Estado:\s*(\S+)') { $r.replica = $Matches[1] }
        elseif ($l -match '^\s*[\{\[]') { $r.body = $l }
    }
    return [pscustomobject]$r
}

function Mostrar($r) {
    $color = if ($r.http -match '^2') { 'Green' } else { 'Yellow' }
    Write-Host ("HTTP {0}   X-Cliente: {1}   X-Instance: {2}   X-DB: {3}" -f $r.http, $r.cliente, $r.instance, $r.db) -ForegroundColor $color -NoNewline
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

Titulo '6. Gateway - limite de peticiones del cliente WEB: 60 en paralelo (limite 10/s, rafaga 20)'
# En paralelo: una por una, curl.exe en Windows va a ~10 req/s (justo el promedio permitido) y no aparece el 429.
$tmpRl = Join-Path $env:TEMP 'demo-rate-limit'
New-Item -ItemType Directory -Force $tmpRl | Out-Null
$codigos = curl.exe -s -Z --parallel-immediate --parallel-max 60 -m 5 -w '%{http_code}\n' -o "$tmpRl\r_#1.txt" -H "X-API-Key: $ApiKey" "$Url/api/v1/avisos?limit=1&n=[1-60]"
Remove-Item -Recurse -Force $tmpRl -ErrorAction SilentlyContinue
$codigos | Group-Object | Sort-Object Name | ForEach-Object { Write-Host ("  HTTP {0}: {1} veces" -f $_.Name, $_.Count) }

Titulo '7. El limite es POR CLIENTE: la app movil sigue pasando aunque la web este limitada'
Mostrar (Pedir 'GET' '/api/v1/avisos?limit=1' -Key $ApiKeyMovil)

Remove-Item $cuerpo -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'Demo terminada.' -ForegroundColor Green
