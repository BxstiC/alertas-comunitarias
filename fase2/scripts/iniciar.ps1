# Levanta todo el sistema con un doble clic (lo llama INICIAR.bat).
# 1. Abre Docker Desktop si no esta corriendo y espera a que responda.
# 2. Crea .env desde .env.example si no existe.
# 3. docker compose up -d --build y espera a que el gateway responda.
# 4. Ejecuta la demo (escritura, lectura y cabeceras).
# Con -DesdeCero (REINICIAR_DESDE_CERO.bat) antes BORRA los volumenes de la base.
param([switch]$DesdeCero)
. "$PSScriptRoot\comun.ps1"

function Paso([string]$t) { Write-Host ''; Write-Host "==> $t" -ForegroundColor Cyan }
function Fallar([string]$t) { Write-Host ''; Write-Host "ERROR: $t" -ForegroundColor Red; exit 1 }

# ---------- 1. Docker ----------
Paso 'Comprobando Docker'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fallar 'Docker no esta instalado (no se encontro el comando docker). Instala Docker Desktop.'
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $candidatos = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    )
    $exe = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) { Fallar 'Docker Desktop no esta corriendo y no se encontro para abrirlo. Abrelo a mano y vuelve a ejecutar.' }
    Write-Host 'Docker Desktop no esta corriendo: abriendolo...'
    Start-Process $exe
    $limite = (Get-Date).AddMinutes(3)
    do {
        Start-Sleep 3
        Write-Host '.' -NoNewline
        docker info *> $null
    } while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $limite)
    Write-Host ''
    if ($LASTEXITCODE -ne 0) { Fallar 'Docker no respondio en 3 minutos.' }
}
Write-Host 'Docker listo.' -ForegroundColor Green

# ---------- 2. .env ----------
if (-not (Test-Path (Join-Path $Raiz '.env'))) {
    Copy-Item (Join-Path $Raiz '.env.example') (Join-Path $Raiz '.env')
    Write-Host 'Se creo .env a partir de .env.example.'
}
$ApiKey = Leer-Env 'API_KEY' $ApiKey

if ($DesdeCero) {
    Paso 'Borrando contenedores y volumenes (reinicio desde cero)'
    Escribir-Env 'DB_PRIMARY_HOST' ''
    docker compose down -v
}

# ---------- 3. Levantar ----------
Paso 'Levantando los contenedores (la primera vez descarga imagenes y tarda unos minutos)'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fallar 'docker compose up fallo. Revisa el mensaje de arriba.' }

Paso 'Esperando a que el gateway responda'
$limite = (Get-Date).AddMinutes(3)
$listo = $false
do {
    Start-Sleep 2
    Write-Host '.' -NoNewline
    $codigo = curl.exe -s -o NUL -m 3 -w '%{http_code}' -H "X-API-Key: $ApiKey" http://localhost:8000/api/v1/avisos
    $listo = ($codigo -eq '200')
} while (-not $listo -and (Get-Date) -lt $limite)
Write-Host ''
docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
if (-not $listo) { Fallar 'El sistema no respondio en 3 minutos. Mira los logs con: docker compose logs' }

# Si la replica viene de la version de la Fase 2, no se conecta por la red "replicacion".
$conninfo = Sql 'db-replica' 'SHOW primary_conninfo'
if ($conninfo -and ($conninfo -notmatch 'db-primary-repl') -and ((Servicio-Primaria) -eq 'db-primary')) {
    Write-Host ''
    Write-Host 'AVISO: la replica no apunta a db-primary-repl (debio corregirse sola al arrancar).' -ForegroundColor Yellow
    Write-Host 'Revisa: docker compose logs db-replica. Si persiste, ejecuta REINICIAR_DESDE_CERO.bat.' -ForegroundColor Yellow
}

# Libera la cache que dejo la construccion de imagenes en la VM de Docker (vmmemWSL).
# No afecta a los contenedores; si falla (otro equipo sin WSL) se ignora.
wsl -d docker-desktop -u root sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' *> $null

Write-Host ''
Write-Host 'Sistema arriba en http://localhost:8000' -ForegroundColor Green

# ---------- 4. Demo ----------
& "$PSScriptRoot\demo.ps1"
