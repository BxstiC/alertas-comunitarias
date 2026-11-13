# Evidencias de la Fase 2 · La arquitectura corre

Todas las salidas de este documento son reales. Se obtuvieron el 13 de noviembre de 2026 en PowerShell (Windows 11, Docker Desktop 29.9.2) con el sistema levantado con `docker compose up -d`. El valor de la API key se lee desde `.env` y no se imprime.

**Recorrido de una petición:**

```text
Cliente (curl) ──► Traefik :8000 (gateway) ──► NGINX (balanceador) ──► app-1 / app-2 ──► db-primary ──streaming──► db-replica
```

Cada componente agrega una cabecera a la respuesta, así que el recorrido se ve sin mirar el código:

| Cabecera | Quién la pone | Qué demuestra |
|---|---|---|
| `X-Gateway: traefik` | API gateway (Traefik) | La petición entró por el gateway |
| `X-Balanceador: nginx` | Balanceador (NGINX) | El gateway la mandó al balanceador |
| `X-Instance: app-1` / `app-2` | Instancia de la aplicación | Qué instancia respondió |
| `X-DB: primary` / `replica` | Instancia de la aplicación | A qué base iría la consulta (en esta fase el servicio es de prueba) |

---

## 0. Preparación

```powershell
cd fase2
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
```

Salida de `docker compose ps` (7 servicios en `Up`; los 6 que tienen healthcheck aparecen `healthy`):

```text
NAME                   IMAGE                COMMAND                  SERVICE        CREATED              STATUS                        PORTS
fase2-api-key-auth-1   fase2-api-key-auth   "python auth.py"         api-key-auth   About a minute ago   Up About a minute (healthy)   8080/tcp
fase2-app-1-1          fase2-app-1          "uvicorn main:app --…"   app-1          About a minute ago   Up 42 seconds (healthy)       8000/tcp
fase2-app-2-1          fase2-app-2          "uvicorn main:app --…"   app-2          About a minute ago   Up About a minute (healthy)   8000/tcp
fase2-balanceador-1    nginx:1.27-alpine    "/docker-entrypoint.…"   balanceador    About a minute ago   Up About a minute (healthy)   80/tcp
fase2-db-primary-1     postgres:16-alpine   "docker-entrypoint.s…"   db-primary     About a minute ago   Up About a minute (healthy)   5432/tcp
fase2-db-replica-1     fase2-db-replica     "/usr/local/bin/repl…"   db-replica     About a minute ago   Up About a minute (healthy)   5432/tcp
fase2-gateway-1        traefik:v3.3         "/entrypoint.sh --co…"   gateway        About a minute ago   Up About a minute             0.0.0.0:8000->80/tcp, [::]:8000->80/tcp
```

Variable con la API key, sin mostrarla en pantalla (se usa en los pasos siguientes):

```powershell
$apiKey = ((Get-Content .env | Where-Object { $_ -match '^API_KEY=' }) -replace '^API_KEY=', '').Trim()
```

---

## 1. Las peticiones llegan por el gateway y no directamente a las instancias

**1.a. Solo el gateway publica un puerto en el host.** En la columna `PORTS`, solo `gateway` tiene `0.0.0.0:8000->80/tcp`. Las apps, el balanceador y las bases no publican puertos.

```powershell
docker compose ps --format "table {{.Service}}\t{{.Ports}}"
```

```text
SERVICE        PORTS
api-key-auth   8080/tcp
app-1          8000/tcp
app-2          8000/tcp
balanceador    80/tcp
db-primary     5432/tcp
db-replica     5432/tcp
gateway        0.0.0.0:8000->80/tcp, [::]:8000->80/tcp
```

**1.b. Docker confirma que las instancias y el balanceador no están expuestos al host:**

```powershell
docker compose port app-1 8000
docker compose port app-2 8000
docker compose port balanceador 80
```

```text
:0
:0
:0
```

> `:0` significa que el puerto **no está publicado** en el host. La única forma de llegar desde fuera es `localhost:8000`, que es Traefik.

**1.c. Una petición por el gateway muestra el recorrido completo en las cabeceras:**

```powershell
curl.exe -i -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos
```

```text
HTTP/1.1 200 OK
Content-Length: 61
Content-Type: application/json
Date: Fri, 13 Nov 2026 11:48:17 GMT
Server: nginx/1.27.5
X-Balanceador: nginx
X-Db: replica
X-Gateway: traefik
X-Instance: app-1

{"message":"Endpoint temporal; lógica de negocio pendiente"}
```

> Resultado: `200 OK` con `X-Gateway: traefik`, `X-Balanceador: nginx`, `X-Instance` y `X-DB` (Traefik la reescribe como `X-Db`; los nombres de cabecera HTTP no distinguen mayúsculas).

**1.d. Las bases de datos están en una red interna (`data`, `internal: true`) a la que el gateway no tiene acceso:**

```powershell
docker network ls --filter name=fase2
docker network inspect fase2_data --format "{{.Internal}}"
```

```text
NETWORK ID     NAME          DRIVER    SCOPE
0245b3a40627   fase2_data    bridge    local
bcbe524eb751   fase2_proxy   bridge    local
true
```

---

## 2. El balanceador alterna entre las instancias

**2.a. Round robin:** se hacen 6 peticiones seguidas y se muestra solo la cabecera `X-Instance`.

```powershell
1..6 | ForEach-Object {
    $h = curl.exe -s -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos
    "Peticion $_ -> " + ($h | Select-String '^X-Instance').Line
}
```

```text
Peticion 1 -> X-Instance: app-2
Peticion 2 -> X-Instance: app-1
Peticion 3 -> X-Instance: app-2
Peticion 4 -> X-Instance: app-1
Peticion 5 -> X-Instance: app-2
Peticion 6 -> X-Instance: app-1
```

> Resultado: `X-Instance` alterna entre `app-1` y `app-2` (round robin).

**2.b. El balanceador retira una instancia caída:** se apaga `app-1` y se repiten las peticiones.

```powershell
docker compose stop app-1
1..6 | ForEach-Object {
    $h = curl.exe -s -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos
    "Peticion $_ -> " + (($h | Select-String '^HTTP/|^X-Instance').Line -join ' | ')
}
```

```text
 Container fase2-app-1-1 Stopping
 Container fase2-app-1-1 Stopped
Peticion 1 -> HTTP/1.1 200 OK | X-Instance: app-2
Peticion 2 -> HTTP/1.1 200 OK | X-Instance: app-2
Peticion 3 -> HTTP/1.1 200 OK | X-Instance: app-2
Peticion 4 -> HTTP/1.1 200 OK | X-Instance: app-2
Peticion 5 -> HTTP/1.1 200 OK | X-Instance: app-2
Peticion 6 -> HTTP/1.1 200 OK | X-Instance: app-2
```

> Resultado: las 6 peticiones responden `200` desde `app-2`, sin errores para el cliente. NGINX detecta el fallo de conexión con `app-1`, reintenta en `app-2` (`proxy_next_upstream`) y deja de enviarle tráfico durante `fail_timeout=10s` (`max_fails=2`).

**2.c. Se vuelve a levantar `app-1` y el balanceo se recupera:**

```powershell
docker compose start app-1
Start-Sleep -Seconds 15
1..4 | ForEach-Object {
    $h = curl.exe -s -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos
    "Peticion $_ -> " + ($h | Select-String '^X-Instance').Line
}
```

```text
 Container fase2-app-1-1 Starting
 Container fase2-app-1-1 Started
Peticion 1 -> X-Instance: app-1
Peticion 2 -> X-Instance: app-2
Peticion 3 -> X-Instance: app-1
Peticion 4 -> X-Instance: app-2
```

---

## 3. Funciones del gateway: API key y límite de peticiones

### 3.a. API key: un caso que se rechaza y uno que pasa

Sin API key, **se rechaza** (Traefik responde sin llegar al balanceador, así que no aparece `X-Balanceador` ni `X-Instance`):

```powershell
curl.exe -i http://localhost:8000/api/v1/avisos
```

```text
HTTP/1.1 401 Unauthorized
Date: Fri, 13 Nov 2026 11:48:17 GMT
Server: BaseHTTP/0.6 Python/3.12.16
X-Gateway: traefik
Content-Length: 27

API key required or invalid
```

Con una API key incorrecta, **se rechaza**:

```powershell
curl.exe -i -H "X-API-Key: clave-incorrecta-de-prueba-123456" http://localhost:8000/api/v1/avisos
```

```text
HTTP/1.1 401 Unauthorized
Date: Fri, 13 Nov 2026 11:48:17 GMT
Server: BaseHTTP/0.6 Python/3.12.16
X-Gateway: traefik
Content-Length: 27

API key required or invalid
```

Con la API key correcta, **pasa**:

```powershell
curl.exe -i -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos
```

```text
HTTP/1.1 200 OK
Content-Length: 61
Content-Type: application/json
Date: Fri, 13 Nov 2026 11:48:17 GMT
Server: nginx/1.27.5
X-Balanceador: nginx
X-Db: replica
X-Gateway: traefik
X-Instance: app-2

{"message":"Endpoint temporal; lógica de negocio pendiente"}
```

> Resultado: `401`, `401` y `200`. En los rechazos aparece `X-Gateway` pero no `X-Balanceador` ni `X-Instance`: el gateway corta la petición antes de que llegue al balanceador.

### 3.b. Límite de peticiones por cliente (10 req/s con ráfaga de 20)

Se mandan 40 peticiones lo más rápido posible con una sola conexión de curl y se cuentan los códigos HTTP:

```powershell
curl.exe -s -w "\nHTTP %{http_code}\n" -H "X-API-Key: $apiKey" "http://localhost:8000/api/v1/avisos?n=[1-40]" |
    Select-String '^HTTP' | Group-Object Line | Select-Object Name, Count
```

```text
Name     Count
----     -----
HTTP 200    23
HTTP 429    17
```

> Resultado: 23 respuestas `200` (la ráfaga de 20 más lo que se repuso mientras duró la prueba) y 17 `429 Too Many Requests`. El límite se cuenta por API key (`sourceCriterion: requestHeaderName: X-API-Key`).

---

## 4. La réplica sigue a la primaria

> Si cambiaron `POSTGRES_USER` o `POSTGRES_DB` en `.env`, reemplacen `app_user` y `avisos` en los comandos.

**4.a. La primaria tiene una réplica conectada por streaming:**

```powershell
docker compose exec db-primary psql -U app_user -d avisos -c "SELECT client_addr, usename, state, sync_state FROM pg_stat_replication;"
```

```text
 client_addr |  usename   |   state   | sync_state
-------------+------------+-----------+------------
 172.18.0.3  | replicator | streaming | async
(1 row)
```

> Resultado: la réplica está conectada con el usuario `replicator` en estado `streaming` (asíncrono).

**4.b. La réplica está en modo recuperación (standby) y la primaria no:**

```powershell
docker compose exec db-primary psql -U app_user -d avisos -c "SELECT pg_is_in_recovery() AS es_replica;"
docker compose exec db-replica psql -U app_user -d avisos -c "SELECT pg_is_in_recovery() AS es_replica;"
```

```text
 es_replica
------------
 f
(1 row)

 es_replica
------------
 t
(1 row)
```

> Resultado: `f` en la primaria y `t` en la réplica.

**4.c. Se escribe en la primaria:**

```powershell
docker compose exec db-primary psql -U app_user -d avisos -c "CREATE TABLE IF NOT EXISTS prueba_replica (id SERIAL PRIMARY KEY, mensaje TEXT NOT NULL, creado_en TIMESTAMPTZ NOT NULL DEFAULT now());"
docker compose exec db-primary psql -U app_user -d avisos -c "INSERT INTO prueba_replica (mensaje) VALUES ('escrito en la primaria - fase 2') RETURNING *;"
```

```text
CREATE TABLE
 id |             mensaje             |          creado_en
----+---------------------------------+------------------------------
  1 | escrito en la primaria - fase 2 | 2026-11-13 11:49:09.32673+00
(1 row)

INSERT 0 1
```

**4.d. El dato aparece en la réplica:**

```powershell
docker compose exec db-replica psql -U app_user -d avisos -c "SELECT * FROM prueba_replica ORDER BY id DESC LIMIT 5;"
```

```text
 id |             mensaje             |          creado_en
----+---------------------------------+------------------------------
  1 | escrito en la primaria - fase 2 | 2026-11-13 11:49:09.32673+00
(1 row)
```

> Resultado: la misma fila (mismo `id`, `mensaje` y `creado_en`) que se insertó en la primaria.

**4.e. La réplica es de solo lectura (no acepta escrituras):**

```powershell
docker compose exec db-replica psql -U app_user -d avisos -c "INSERT INTO prueba_replica (mensaje) VALUES ('intento en la replica');"
```

```text
ERROR:  cannot execute INSERT in a read-only transaction
```

> Resultado: la réplica rechaza la escritura.

**4.f. Atraso de la réplica (lag), medido en la primaria justo después de una escritura:**

```powershell
docker compose exec db-primary psql -U app_user -d avisos -c "INSERT INTO prueba_replica (mensaje) VALUES ('medicion de atraso');"
docker compose exec db-primary psql -U app_user -d avisos -c "SELECT usename, write_lag, flush_lag, replay_lag, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_pendientes FROM pg_stat_replication;"
```

```text
  usename   |    write_lag    |    flush_lag    |   replay_lag    | bytes_pendientes
------------+-----------------+-----------------+-----------------+------------------
 replicator | 00:00:00.000368 | 00:00:00.001658 | 00:00:00.001814 |                0
(1 row)
```

> Resultado: la réplica aplicó la escritura en ~1,8 ms (`replay_lag`) y no quedan bytes pendientes. Es un primer dato para el RPO que se medirá en la Fase 3.
>
> Nota: `now() - pg_last_xact_replay_timestamp()` en la réplica **no** sirve para medir el atraso, porque mide el tiempo desde la última transacción y crece aunque la réplica esté al día si no hay escrituras.

---

## Lista de comprobación

- [x] `docker compose up -d` levanta los 7 servicios.
- [x] Solo el gateway publica un puerto (8000). Las apps, el balanceador y las bases no son accesibles desde el host.
- [x] Las respuestas muestran `X-Gateway`, `X-Balanceador` y `X-Instance`.
- [x] `X-Instance` alterna entre `app-1` y `app-2`.
- [x] Con `app-1` apagada el sistema sigue respondiendo desde `app-2`.
- [x] Sin API key o con una incorrecta: `401`. Con la API key correcta: `200`.
- [x] Al superar el límite de peticiones aparece `429`.
- [x] `pg_stat_replication` muestra la réplica en `streaming`.
- [x] Una fila insertada en la primaria aparece en la réplica.
- [x] La réplica rechaza escrituras.
