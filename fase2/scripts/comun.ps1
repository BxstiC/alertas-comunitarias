# Funciones compartidas por los scripts de pruebas de falla.
# Uso: . "$PSScriptRoot\comun.ps1"   (se carga con punto, no se ejecuta solo)

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

# Lee una variable de .env (o de .env.example si no hay .env). Devuelve $Defecto si no existe.
function Leer-Env([string]$Nombre, [string]$Defecto = '') {
    foreach ($archivo in @('.env', '.env.example')) {
        $ruta = Join-Path $Raiz $archivo
        if (Test-Path $ruta) {
            $linea = Get-Content $ruta | Where-Object { $_ -match "^$Nombre=" } | Select-Object -First 1
            if ($linea) { return ($linea -replace "^$Nombre=", '').Trim() }
            if ($archivo -eq '.env') { return $Defecto }
        }
    }
    return $Defecto
}

# Escribe (o reemplaza) una variable en .env, creandolo desde .env.example si no existe.
function Escribir-Env([string]$Nombre, [string]$Valor) {
    $ruta = Join-Path $Raiz '.env'
    if (-not (Test-Path $ruta)) { Copy-Item (Join-Path $Raiz '.env.example') $ruta }
    $lineas = @(Get-Content $ruta | Where-Object { $_ -notmatch "^$Nombre=" })
    if ($Valor) { $lineas += "$Nombre=$Valor" }
    Set-Content -Path $ruta -Value $lineas -Encoding ascii
}

function Hora { (Get-Date).ToString('HH:mm:ss.fff') }

$DbUser = Leer-Env 'POSTGRES_USER' 'app_user'
$DbName = Leer-Env 'POSTGRES_DB' 'avisos'
$ApiKey = Leer-Env 'API_KEY' 'dev-api-key-change-me-to-a-long-random-value'

# Servicio que hoy actua como primaria (cambia despues de scripts\failover.ps1).
function Servicio-Primaria {
    $h = Leer-Env 'DB_PRIMARY_HOST' 'db-primary'
    if ($h) { return $h } else { return 'db-primary' }
}

# Ejecuta SQL con psql dentro de un contenedor de base de datos y devuelve las filas.
function Sql([string]$Servicio, [string]$Consulta) {
    docker compose exec -T $Servicio psql -U $DbUser -d $DbName -tAc $Consulta
}
