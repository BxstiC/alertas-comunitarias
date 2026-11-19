# Genera escrituras continuas por el gateway y registra cada respuesta en un CSV.
# Sirve para medir RTO (cuanto tiempo no se pudo escribir) y RPO (que avisos
# confirmados con 201 se perdieron) en la prueba de falla 3.
#
# Uso (desde la carpeta fase2):
#   powershell -ExecutionPolicy Bypass -File scripts\escrituras.ps1 -Segundos 60
param(
    [int]$Segundos = 60,
    [int]$IntervaloMs = 200,
    [string]$Salida = 'escrituras.csv',
    [string]$Url = 'http://localhost:8000/api/v1/avisos'
)
. "$PSScriptRoot\comun.ps1"

$cuerpo = Join-Path $env:TEMP "aviso-$PID.json"
$respuesta = Join-Path $env:TEMP "respuesta-$PID.json"
Set-Content -Path $Salida -Value 'ts,n,http,id,instancia' -Encoding ascii

$fin = (Get-Date).AddSeconds($Segundos)
$n = 0
Write-Host "Escribiendo un aviso cada $IntervaloMs ms durante $Segundos s. Resultado en $Salida"
while ((Get-Date) -lt $fin) {
    $n++
    $json = '{"titulo":"Prueba de escritura ' + $n + '","descripcion":"Carga de la prueba de falla","categoria":"otro"}'
    [IO.File]::WriteAllText($cuerpo, $json)
    if (Test-Path $respuesta) { Remove-Item $respuesta }

    $ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fff')
    $salidaCurl = curl.exe -s -m 3 -o $respuesta -D - -w 'HTTP=%{http_code}' -X POST `
        -H 'Content-Type: application/json' -H "X-API-Key: $ApiKey" --data-binary "@$cuerpo" $Url

    $codigo = '000'
    $instancia = ''
    foreach ($l in $salidaCurl) {
        if ($l -match 'HTTP=(\d{3})') { $codigo = $Matches[1] }
        if ($l -match '^X-Instance:\s*(\S+)') { $instancia = $Matches[1] }
    }
    $id = ''
    if ($codigo -eq '201' -and (Test-Path $respuesta)) {
        $id = (Get-Content $respuesta -Raw | ConvertFrom-Json).id
    }
    Add-Content -Path $Salida -Value "$ts,$n,$codigo,$id,$instancia" -Encoding ascii
    Write-Host "$ts  HTTP $codigo  id=$id  $instancia"
    Start-Sleep -Milliseconds $IntervaloMs
}
Remove-Item $cuerpo, $respuesta -ErrorAction SilentlyContinue
Write-Host "Listo: $n escrituras registradas en $Salida"
