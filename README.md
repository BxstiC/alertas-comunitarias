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
| `app-1`, `app-2` | propia (FastAPI) | Instancias sin estado y idénticas. Responden `X-Instance` y `X-DB` | — |
| `db-primary` | `postgres:16-alpine` | Recibe las escrituras | — |
| `db-replica` | `postgres:16-alpine` | Réplica por streaming de solo lectura | — |

Las bases están en una red Docker interna (`data`) a la que no llegan ni el gateway ni el balanceador.

## Requisitos

- Docker Desktop (o Docker Engine) con Docker Compose v2, **en ejecución**.
- Puerto `8000` libre en el equipo.
- Git.

## Cómo levantar el sistema

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

## Cómo probarlo

```powershell
# API key desde .env, sin imprimirla
$apiKey = ((Get-Content .env | Where-Object { $_ -match '^API_KEY=' }) -replace '^API_KEY=', '').Trim()

# Salud (sin API key)
curl.exe -i http://localhost:8000/health

# Sin API key -> 401
curl.exe -i http://localhost:8000/api/v1/avisos

# Lectura -> 200, X-DB: replica
curl.exe -i -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos

# Escritura -> 200, X-DB: primary
curl.exe -i -X POST -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos

# Balanceo: X-Instance alterna entre app-1 y app-2
1..6 | ForEach-Object { (curl.exe -s -D - -o NUL -H "X-API-Key: $apiKey" http://localhost:8000/api/v1/avisos | Select-String '^X-Instance').Line }
```

Las pruebas completas con sus salidas (gateway como única entrada, balanceo y retiro de una instancia caída, API key, límite de peticiones y replicación) están en [docs/fase2/EVIDENCIAS.md](docs/fase2/EVIDENCIAS.md).

## Decisiones de configuración (Fase 2)

- **Gateway y balanceador separados:** Traefik solo apunta a un backend (`http://balanceador:80`), así que el reparto entre instancias lo hace únicamente NGINX.
- **Funciones del gateway:**
  1. Enrutamiento por ruta: `PathPrefix(/api/v1/)` va a la API protegida y `/health` queda abierto.
  2. API key: middleware `forwardAuth` hacia `api-key-auth`, que compara `X-API-Key` en tiempo constante (`hmac.compare_digest`).
  3. Límite de peticiones: 10 req/s en promedio con ráfaga de 20, contado **por API key**. Es un valor bajo a propósito para poder demostrar el `429`.
- **Detección de caídas en el balanceador:** NGINX OSS usa comprobaciones pasivas (`max_fails=2 fail_timeout=10s`). Si una instancia falla, la petición se reintenta en la otra (`proxy_next_upstream`) y la instancia caída queda fuera durante 10 s.
- **Replicación:** streaming asíncrono. La primaria crea el rol `replicator` al inicializarse (`db/primary/init`), y la réplica hace `pg_basebackup --write-recovery-conf` en su primer arranque (`db/replica/replica-entrypoint.sh`). La primaria guarda `wal_keep_size=256MB` de WAL para que la réplica pueda ponerse al día tras una desconexión corta.
- **Cabeceras de trazabilidad:** `X-Gateway` (Traefik), `X-Balanceador` (NGINX), `X-Instance` y `X-DB` (aplicación).

## Comandos útiles

```powershell
docker compose logs -f gateway balanceador     # ver tráfico
docker compose stop app-1                      # simular caída de una instancia
docker compose start app-1
docker compose down                            # detener (conserva los datos)
docker compose down -v                         # detener y BORRAR los volúmenes (reinicio desde cero)
```

## Limitaciones conocidas (Fase 2)

- Las instancias son un **servicio de prueba**: devuelven `X-Instance` y `X-DB`, pero todavía no consultan la base. La lógica real llega en la Fase 3.
- La replicación es **asíncrona**: ante una caída de la primaria se pueden perder las últimas transacciones aún no enviadas (RPO > 0). La promoción de la réplica es manual.
- Gateway, balanceador y primaria son instancias únicas, así que son **puntos únicos de falla** en este despliegue.
- Si se borra solo el volumen de la primaria (o se cambian las credenciales de replicación) hay que recrear también la réplica con `docker compose down -v`.
- Los scripts `.sh` deben tener finales de línea LF. `.gitattributes` lo fuerza al clonar en Windows.

## Estructura

```text
.
├── README.md
├── .gitignore / .gitattributes
├── docs/
│   ├── fase1/   (PROBLEMA.md, DISEÑO.md, REQUISITOS.md, ESTIMACION_CARGA.md, diagramas/)
│   └── fase2/   (EVIDENCIAS.md)
└── fase2/
    ├── docker-compose.yml
    ├── .env.example
    ├── gateway/       (traefik.yml, dynamic.yml, auth/)
    ├── balanceador/   (nginx.conf)
    ├── app/           (main.py, Dockerfile)
    └── db/            (primary/, replica/)
```
