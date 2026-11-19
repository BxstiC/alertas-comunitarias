# Alertas Vecinales · Arquitectura con gateway, balanceador y réplica de base de datos

Proyecto individual ISI601 · Taller de Diseño de Sistemas.

```text
Cliente ──► Traefik (API gateway, :8000) ──► NGINX (balanceador) ──► app-1 / app-2 (FastAPI)
                                                                        │ escrituras      │ lecturas
                                                                        ▼                 ▼
                                                                   db-primary ──streaming──► db-replica
                                                                   (PostgreSQL 16)          (PostgreSQL 16)
```

| Servicio | Imagen | Rol | Puerto en el host |
|---|---|---|---|
| `gateway` | `traefik:v3.3` | Única entrada. Enruta `/api/v1/...`, exige API key y limita peticiones por cliente | **8000** |
| `api-key-auth` | propia (Python) | Valida `X-API-Key` para Traefik (`forwardAuth`) | — |
| `balanceador` | `nginx:1.27-alpine` | Round robin entre `app-1` y `app-2` y retira una instancia caída | — |
| `app-1`, `app-2` | propia (FastAPI + asyncpg) | API de avisos vecinales. Instancias sin estado e idénticas. Escriben en la primaria y leen de la réplica. Responden `X-Instance` y `X-DB` | — |
| `db-primary` | `postgres:16-alpine` | Recibe las escrituras | — |
| `db-replica` | `postgres:16-alpine` | Réplica por streaming de solo lectura. Recibe el WAL por la red exclusiva `replicacion` | — |

Las bases están en una red Docker interna (`data`) a la que no llegan ni el gateway ni el balanceador. El streaming entre primaria y réplica va por otra red interna (`replicacion`), así se puede cortar la replicación sin cortar a las apps (prueba de falla 2).

## Requisitos

- Docker Desktop (o Docker Engine) con Docker Compose v2, **en ejecución**.
- Puerto `8000` libre en el equipo.
- Git.

## Cómo levantar el sistema

### Con doble clic (Windows)

En la raíz del repositorio:

| Archivo | Qué hace |
|---|---|
| `INICIAR.bat` | Abre Docker Desktop si está cerrado, crea `.env` si falta, ejecuta `docker compose up -d --build`, espera a que el gateway responda y corre la demo |
| `DEMO.bat` | Escritura, lectura, cabeceras `X-Instance`/`X-DB`, balanceo, API key (401) y límite de peticiones (429) |
| `DETENER.bat` | `docker compose stop` (conserva los datos) |
| `REINICIAR_DESDE_CERO.bat` | Pide confirmación, **borra los volúmenes** y levanta todo de nuevo |

### Por consola

```powershell
git clone <URL-DEL-REPOSITORIO> alertas-vecinales
cd alertas-vecinales\fase2
Copy-Item .env.example .env      # opcional: sin .env se usan los valores de ejemplo
docker compose up -d
docker compose ps
```

En Linux o macOS se usa `cp .env.example .env` en lugar de `Copy-Item`.

La primera vez Docker construye las imágenes propias y la réplica clona a la primaria con `pg_basebackup`, lo que toma entre 30 y 60 segundos. El sistema está listo cuando `docker compose ps` muestra los 7 servicios en `Up` (los 6 con healthcheck como `healthy`; el gateway no tiene healthcheck).

> **Secretos:** `.env` está en `.gitignore` y no se sube al repositorio. `.env.example` solo contiene valores de ejemplo de clase. Para un uso real se debe cambiar `API_KEY` (mínimo 24 caracteres) y las contraseñas.


> **Si ya tenías levantada la versión de la Fase 2:** en la Fase 3 la réplica se conecta a la primaria por otro host (`db-primary-repl`). Al arrancar, `replica-entrypoint.sh` reescribe `primary_conninfo` con ese host, así que basta con `docker compose up -d --build`. Si `docker compose logs db-replica` sigue mostrando errores de conexión, recrearla desde cero: `powershell -ExecutionPolicy Bypass -File scripts\restaurar.ps1 -Confirmar` (borra los datos de prueba).

## API

Todas las rutas `/api/v1/...` exigen la cabecera `X-API-Key`. `/health` queda abierta.

| Método y ruta | Qué hace | Base | `X-DB` |
|---|---|---|---|
| `GET /health` | Estado e `instance_id` de la instancia | ninguna | `none` |
| `POST /api/v1/avisos` | Publica un aviso (`titulo`, `descripcion`, `categoria`, `fecha` opcional) | primaria | `primary` |
| `GET /api/v1/avisos?categoria=&limit=&offset=` | Avisos vigentes (últimos 7 días), más recientes primero | réplica | `replica` (o `primary` si la réplica falla) |
| `GET /api/v1/avisos/{id}` | Detalle de un aviso | réplica | `replica` (o `primary`, ver abajo) |
| `GET /api/v1/replicacion` | Diagnóstico: estado de la réplica, último id en cada base, bytes pendientes | ambas | `primary+replica` |

Categorías válidas: `corte_servicio`, `emergencia`, `seguridad`, `objeto_perdido`, `actividad_comunitaria`, `otro`.

Cabeceras de respuesta:

| Cabecera | Quién la pone | Valor |
|---|---|---|
| `X-Gateway` | Traefik | `traefik` |
| `X-Balanceador` | NGINX | `nginx` |
| `X-Instance` | App | `app-1` o `app-2` |
| `X-DB` | App | `primary` o `replica`: la base que **realmente** atendió la consulta |
| `X-Replica-Estado` | App (lecturas) | `streaming`, `desconectada`, `pausada`, `caida` o `promovida` |
| `X-Datos-Desactualizados` | App (lecturas) | `posible`: solo si la primaria está caída y la réplica desconectada |

## Cómo probarlo

Desde la carpeta `fase2`:

```powershell
# API key desde .env (o .env.example si no se creó .env), sin imprimirla
$envFile = if (Test-Path .env) { '.env' } else { '.env.example' }
$apiKey = ((Get-Content $envFile | Where-Object { $_ -match '^API_KEY=' }) -replace '^API_KEY=', '').Trim()

# Salud (sin API key)
curl.exe -i http://localhost:8000/health

# Sin API key -> 401
curl.exe -i http://localhost:8000/api/v1/avisos

# Escritura -> 201, X-DB: primary
'{"titulo":"Corte de agua","descripcion":"Sin agua de 09:00 a 14:00 en Los Aromos","categoria":"corte_servicio"}' |
  Set-Content -Encoding ascii aviso.json
curl.exe -i -X POST -H "Content-Type: application/json" -H "X-API-Key: $apiKey" --data-binary "@aviso.json" http://localhost:8000/api/v1/avisos

# Lectura -> 200, X-DB: replica
curl.exe -i -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos
curl.exe -i -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos/1

# Balanceo: X-Instance alterna entre app-1 y app-2
1..6 | ForEach-Object { (curl.exe -s -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos | Select-String '^X-Instance').Line }

# Límite de peticiones: 30 peticiones seguidas -> aparecen 429
1..30 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code} " -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos }

# Estado de la replicación
curl.exe -s -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/replicacion
```

En Linux o macOS se usa `curl` en lugar de `curl.exe` y `cp`/`cat` en lugar de los cmdlets.

- Evidencias de la arquitectura (gateway, balanceo, API key, límite de peticiones y replicación): [docs/fase2/EVIDENCIAS.md](docs/fase2/EVIDENCIAS.md).
- Pruebas de falla con mediciones de RPO y RTO: [docs/fase3/PRUEBAS_DE_FALLA.md](docs/fase3/PRUEBAS_DE_FALLA.md).

## Lectura de lo recién escrito

La replicación es asíncrona, así que justo después de un `POST` la réplica puede no tener todavía el aviso (normalmente son milisegundos; si la replicación se corta, hasta ~10 s). La app lo maneja así:

1. **El `POST` devuelve el aviso completo** (`201` con el cuerpo y la cabecera `Location: /api/v1/avisos/{id}`). El cliente que publica no necesita volver a leerlo para mostrarlo.
2. **`GET /api/v1/avisos/{id}` nunca da un 404 falso.** Si la réplica no lo encuentra, la app lo busca en la primaria antes de responder 404. En ese caso la respuesta sale con `X-DB: primary`.
3. **La lista (`GET /api/v1/avisos`) puede llegar atrasada** por el lag de replicación. Es consistencia eventual, aceptada para un tablón de avisos: los demás vecinos lo ven en milisegundos.
4. **Si la réplica pierde a la primaria** (`X-Replica-Estado: desconectada`), la app deja de leer en ella y lee en la primaria hasta que se recupere. La réplica lo detecta en ≤ 10 s (`wal_receiver_timeout=10s`); en ese lapso la lista puede estar desactualizada (medido: 11,6 s, ver la prueba de falla 2).

## Decisiones de diseño

- **Gateway y balanceador separados:** Traefik solo apunta a un backend (`http://balanceador:80`), así que el reparto entre instancias lo hace únicamente NGINX.
- **Funciones del gateway (las dos activas):**
  1. Enrutamiento por ruta: `PathPrefix(/api/v1/)` va a la API protegida y `/health` queda abierto.
  2. API key: middleware `forwardAuth` hacia `api-key-auth`, que compara `X-API-Key` en tiempo constante (`hmac.compare_digest`).
  3. Límite de peticiones: 10 req/s en promedio con ráfaga de 20, contado **por API key**. Es un valor bajo a propósito para poder demostrar el `429`.
- **Detección de caídas en el balanceador:** NGINX OSS usa comprobaciones pasivas (`max_fails=2 fail_timeout=10s`). Si una instancia no responde, la petición se reintenta en la otra (`proxy_next_upstream error timeout http_502 http_504`). **No** se reintenta ante 500/503: esos errores vienen de la base compartida, y contarlos como falla de la instancia sacaba a las dos apps del balanceo (bug corregido en la Fase 3).
- **Instancias sin estado:** la app no guarda nada en memoria ni en disco. Los pools de conexión se recrean al reiniciar. El esquema se crea en la primaria al arrancar, con un `pg_advisory_xact_lock` para que las dos instancias no choquen.
- **Separación lectura/escritura en la app:** dos pools (`DB_PRIMARY_URL` y `DB_REPLICA_URL`). El de la réplica es `default_transaction_read_only=on` y no abre conexiones al arrancar, así una instancia puede iniciar aunque la réplica esté caída.
- **Lecturas con respaldo:** antes de cada lectura se consulta el estado de la réplica en la misma conexión. Si está desconectada, pausada o caída, se lee en la primaria. Preferimos un dato fresco con más carga en la primaria a un dato viejo.
- **`/health` no consulta la base:** si lo hiciera, una caída de PostgreSQL sacaría a ambas instancias del balanceador a la vez.
- **Replicación asíncrona por streaming:** la primaria crea el rol `replicator` al inicializarse (`db/primary/init`) y la réplica hace `pg_basebackup --write-recovery-conf` en su primer arranque (`db/replica/replica-entrypoint.sh`). `wal_keep_size=256MB` permite que la réplica se ponga al día tras un corte. `wal_receiver_timeout` y `wal_sender_timeout` bajan a 10 s para detectar antes la desconexión.
- **Failover manual con script:** `scripts/failover.ps1` mata la primaria, ejecuta `pg_promote()` y cambia `DB_PRIMARY_HOST=db-replica` en `.env` para que las apps escriban en la réplica promovida (se recrean de a una).

## Pruebas de falla (resumen)

| Prueba | Resultado medido |
|---|---|
| Apagar `app-1` | 0 errores en 161 lecturas; 3 lecturas de ~2 s mientras NGINX detecta la caída |
| Cortar la replicación | 11,6 s de lecturas desactualizadas, después la app lee de la primaria; reconexión en 5,7 s |
| Matar la primaria (réplica al día) | RTO 6,8 s · RPO 0 |
| Matar la primaria (réplica cortada 14 s antes) | RTO 13,3 s · RPO 52 avisos (13,9 s) e ids reutilizados |

Detalle en [docs/fase3/PRUEBAS_DE_FALLA.md](docs/fase3/PRUEBAS_DE_FALLA.md).

## Comandos útiles

Desde la carpeta `fase2`:

```powershell
docker compose logs -f gateway balanceador     # ver tráfico
docker compose logs -f app-1 app-2             # ver de qué base lee cada instancia
docker compose stop app-1                      # simular caída de una instancia
docker compose start app-1
docker compose down                            # detener (conserva los datos)
powershell -ExecutionPolicy Bypass -File scripts\replicacion.ps1 -Accion estado   # estado de la replicación
powershell -ExecutionPolicy Bypass -File scripts\failover.ps1                     # matar primaria y promover réplica
powershell -ExecutionPolicy Bypass -File scripts\restaurar.ps1 -Confirmar         # volver al inicio (BORRA los datos)
```

## Limitaciones

- **Replicación asíncrona:** si la primaria cae con la réplica atrasada, se pierden escrituras ya confirmadas al cliente (medido: 52 avisos con 14 s de atraso). Mitigación: vigilar el lag (`GET /api/v1/replicacion`) y alertar mucho antes del RPO de 5 min.
- **Failover manual:** alguien tiene que ejecutar `failover.ps1`. Mientras tanto no se puede escribir (las lecturas siguen). No hay Patroni ni otro orquestador.
- **Ids reutilizables tras un failover con pérdida:** la secuencia de la réplica promovida puede ir atrasada y repetir ids que la primaria vieja ya había entregado.
- **Split brain:** después del failover no se debe volver a levantar `db-primary` tal cual. Hay que reconstruirla como réplica nueva o usar `restaurar.ps1`.
- **Puntos únicos de falla:** gateway, balanceador y (hasta el failover) la primaria son instancias únicas.
- **Leer de respaldo en la primaria** multiplica su carga (~11 veces con la relación 10:1) mientras la réplica esté fuera. Con una sola réplica no hay otra alternativa.
- **Comprobaciones pasivas en NGINX OSS:** la primera petición a una instancia caída paga hasta 2 s de timeout.
- El límite de peticiones (10 req/s) es bajo a propósito para la demostración.
- Los scripts `.sh` deben tener finales de línea LF. `.gitattributes` lo fuerza al clonar en Windows.

## Estructura

```text
.
├── README.md
├── .gitignore / .gitattributes
├── docs/
│   ├── fase1/   (PROBLEMA.md, DISEÑO.md, REQUISITOS.md, ESTIMACION_CARGA.md, diagramas/)
│   ├── fase2/   (EVIDENCIAS.md)
│   └── fase3/   (PRUEBAS_DE_FALLA.md, datos/ con los CSV de las mediciones)
└── fase2/                (el sistema completo; el nombre viene de la Fase 2)
    ├── docker-compose.yml
    ├── .env.example
    ├── gateway/       (traefik.yml, dynamic.yml, auth/)
    ├── balanceador/   (nginx.conf)
    ├── app/           (app.py, Dockerfile, requirements.txt)
    ├── db/            (primary/, replica/)
    └── scripts/       (escrituras, replicacion, failover, medir-rpo-rto, restaurar)
```
