"""
Servicio de Alertas Comunitarias Vecinales.

- Escrituras  -> base de datos PRIMARIA (cabecera X-DB: primary).
- Lecturas    -> RÉPLICA por streaming (cabecera X-DB: replica).
  Si la réplica está caída o dejó de recibir WAL (posibles datos viejos), la
  lectura se atiende en la primaria (X-DB: primary) y X-Replica-Estado lo explica.
- Todas las respuestas llevan X-Instance con el valor de INSTANCE_ID.
- Stateless: no se guarda nada en memoria ni en disco; todo vive en PostgreSQL.
  (Los pools de conexiones no son estado de negocio: se recrean al reiniciar.)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, AsyncIterator, Awaitable, Callable

import asyncpg
from fastapi import FastAPI, HTTPException, Path, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# ---------------------------------------------------------------------------
# Configuración (solo variables de entorno)
# ---------------------------------------------------------------------------
INSTANCE_ID = os.environ["INSTANCE_ID"]
DB_PRIMARY_URL = os.environ["DB_PRIMARY_URL"]
DB_REPLICA_URL = os.environ["DB_REPLICA_URL"]

# Ventana de vigencia: un aviso es "vigente" si su fecha es posterior a
# (ahora - AVISOS_VIGENCIA_DIAS). Incluye también avisos programados a futuro.
VIGENCIA_DIAS = int(os.getenv("AVISOS_VIGENCIA_DIAS", "7"))
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
DB_COMMAND_TIMEOUT = float(os.getenv("DB_COMMAND_TIMEOUT", "5"))
DB_CONNECT_RETRIES = int(os.getenv("DB_CONNECT_RETRIES", "10"))
# Cortacircuito: si una base no responde, durante estos segundos las lecturas van
# directo a la otra base sin volver a intentarla (con el contenedor apagado, solo resolver
# su nombre tarda segundos, y se pagaría en cada lectura).
DB_PAUSA_S = float(os.getenv("DB_PAUSA_S", "10"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format=f"%(asctime)s %(levelname)s [{INSTANCE_ID}] %(name)s: %(message)s",
)
log = logging.getLogger("avisos")

# Cualquier error de red o de PostgreSQL al hablar con la BD -> 503.
DB_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, asyncio.TimeoutError)

# ---------------------------------------------------------------------------
# Esquema (se ejecuta SOLO en la primaria; la réplica lo recibe por streaming)
# ---------------------------------------------------------------------------
SCHEMA_LOCK_ID = 727_001  # id arbitrario para pg_advisory_xact_lock

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS avisos (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo      VARCHAR(150)  NOT NULL CHECK (char_length(btrim(titulo)) >= 3),
    descripcion VARCHAR(2000) NOT NULL CHECK (char_length(btrim(descripcion)) >= 1),
    categoria   VARCHAR(40)   NOT NULL,
    fecha       TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_avisos_fecha           ON avisos (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_avisos_categoria_fecha ON avisos (categoria, fecha DESC);
"""


# Estado de la réplica, consultado en la MISMA conexión antes de cada lectura.
# - en_recuperacion = false  -> el nodo fue promovido: ya es primaria, sus datos son los vigentes.
# - recibiendo      = false  -> el walreceiver no está conectado a la primaria: los datos
#                               pueden estar desactualizados (comunicación cortada).
# - pausada         = true   -> la réplica recibe WAL pero no lo aplica.
ESTADO_REPLICA_SQL = """
SELECT pg_is_in_recovery() AS en_recuperacion,
       EXISTS (SELECT 1 FROM pg_stat_wal_receiver WHERE status = 'streaming') AS recibiendo,
       CASE WHEN pg_is_in_recovery() THEN pg_is_wal_replay_paused() ELSE false END AS pausada
"""


# ---------------------------------------------------------------------------
# Modelos (Pydantic v2)
# ---------------------------------------------------------------------------
class Categoria(str, Enum):
    corte_servicio = "corte_servicio"
    emergencia = "emergencia"
    seguridad = "seguridad"
    objeto_perdido = "objeto_perdido"
    actividad_comunitaria = "actividad_comunitaria"
    otro = "otro"


class AvisoCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    titulo: str = Field(min_length=3, max_length=150, examples=["Corte de agua"])
    descripcion: str = Field(
        min_length=1, max_length=2000, examples=["Sin agua de 09:00 a 14:00 en calle Los Aromos"]
    )
    categoria: Categoria = Field(examples=["corte_servicio"])
    fecha: datetime | None = Field(
        default=None,
        description="Fecha/hora del aviso (ISO 8601). Si se omite, se usa la hora actual del servidor de BD.",
    )

    @field_validator("fecha")
    @classmethod
    def fecha_con_zona(cls, v: datetime | None) -> datetime | None:
        # Fechas sin zona horaria se interpretan como UTC para evitar ambigüedad.
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class Aviso(BaseModel):
    id: int
    titulo: str
    descripcion: str
    categoria: str
    fecha: datetime


class AvisoLista(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Aviso]


# ---------------------------------------------------------------------------
# Conexión a BD
# ---------------------------------------------------------------------------
async def crear_pool(dsn: str, nombre: str, solo_lectura: bool, min_size: int = DB_POOL_MIN) -> asyncpg.Pool:
    server_settings = {"application_name": f"avisos-{INSTANCE_ID}-{nombre}"}
    if solo_lectura:
        # Defensa adicional: aunque la réplica ya es read-only, el pool también lo es.
        server_settings["default_transaction_read_only"] = "on"

    for intento in range(1, DB_CONNECT_RETRIES + 1):
        try:
            pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=min_size,
                max_size=DB_POOL_MAX,
                command_timeout=DB_COMMAND_TIMEOUT,
                timeout=5,
                server_settings=server_settings,
            )
            log.info("Pool '%s' listo", nombre)
            return pool
        except DB_ERRORS as exc:
            espera = min(2 ** intento, 10)
            log.warning(
                "No se pudo conectar a '%s' (intento %d/%d): %s. Reintento en %ds",
                nombre, intento, DB_CONNECT_RETRIES, exc, espera,
            )
            if intento == DB_CONNECT_RETRIES:
                raise
            await asyncio.sleep(espera)
    raise RuntimeError("inalcanzable")


async def inicializar_esquema(pool: asyncpg.Pool) -> None:
    # El advisory lock evita que app-1 y app-2 creen la tabla a la vez
    # (CREATE TABLE IF NOT EXISTS concurrente puede fallar en PostgreSQL).
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", SCHEMA_LOCK_ID)
            await conn.execute(SCHEMA_SQL)
    log.info("Esquema verificado en la primaria")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.primary = await crear_pool(DB_PRIMARY_URL, "primary", solo_lectura=False)
    try:
        await inicializar_esquema(app.state.primary)
        # min_size=0: el pool de la réplica no abre conexiones al arrancar, así una
        # instancia puede iniciar aunque la réplica esté caída (las lecturas irán a la primaria).
        app.state.replica = await crear_pool(DB_REPLICA_URL, "replica", solo_lectura=True, min_size=0)
    except Exception:
        await app.state.primary.close()
        raise
    try:
        yield
    finally:
        await app.state.replica.close()
        await app.state.primary.close()


# ---------------------------------------------------------------------------
# Middleware: X-Instance en TODAS las respuestas (incluye 404/405/422)
# ---------------------------------------------------------------------------
class InstanceHeaderMiddleware:
    """Middleware ASGI puro (más liviano y seguro que BaseHTTPMiddleware)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # El gateway agrega X-Cliente (web, movil o municipio) según la API key; se devuelve
        # en la respuesta para que se vea qué cliente hizo la petición.
        cliente = dict(scope.get("headers", [])).get(b"x-cliente")

        async def send_con_cabecera(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-instance"]
                headers.append((b"x-instance", INSTANCE_ID.encode("latin-1")))
                if cliente:
                    headers.append((b"x-cliente", cliente))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_con_cabecera)


app = FastAPI(
    title="Alertas Comunitarias Vecinales",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(InstanceHeaderMiddleware)


# ---------------------------------------------------------------------------
# Manejo de errores (siempre con X-Instance; X-DB cuando aplica)
# ---------------------------------------------------------------------------
def x_db_de_ruta(request: Request) -> str:
    if request.url.path.startswith("/api/v1/replicacion"):
        return "primary+replica"
    if request.url.path.startswith("/api/v1/avisos"):
        return "primary" if request.method == "POST" else "replica"
    return "none"


def respuesta_error(request: Request, status_code: int, detail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"detail": detail}),
        headers={"X-Instance": INSTANCE_ID, "X-DB": x_db_de_ruta(request)},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return respuesta_error(request, exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return respuesta_error(request, status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors())


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Este handler corre fuera del middleware, por eso X-Instance se añade aquí explícitamente.
    if isinstance(exc, DB_ERRORS):
        log.error("Error de base de datos en %s %s: %s", request.method, request.url.path, exc)
        return respuesta_error(request, status.HTTP_503_SERVICE_UNAVAILABLE, "Base de datos no disponible")
    log.exception("Error no controlado en %s %s", request.method, request.url.path)
    return respuesta_error(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Error interno")


# ---------------------------------------------------------------------------
# Lecturas: réplica primero, primaria como respaldo
# ---------------------------------------------------------------------------
COLUMNAS = "id, titulo, descripcion, categoria, fecha"

Consulta = Callable[[asyncpg.Connection], Awaitable[Any]]


@dataclass
class Lectura:
    resultado: Any
    x_db: str             # "replica" o "primary": base que respondió
    replica_estado: str   # streaming | promovida | desconectada | pausada | caida

    def cabeceras(self) -> dict[str, str]:
        h = {"X-Instance": INSTANCE_ID, "X-DB": self.x_db, "X-Replica-Estado": self.replica_estado}
        if self.x_db == "replica" and self.replica_estado in ("desconectada", "pausada"):
            # Solo pasa si la primaria TAMBIÉN falló: se entrega el dato viejo, avisando.
            h["X-Datos-Desactualizados"] = "posible"
        return h


def clasificar_replica(fila: asyncpg.Record) -> str:
    if not fila["en_recuperacion"]:
        return "promovida"
    if fila["pausada"]:
        return "pausada"
    if not fila["recibiendo"]:
        return "desconectada"
    return "streaming"


# Hasta cuándo (reloj monotónico) las LECTURAS se saltan cada base. No es dato de negocio:
# es solo el estado de salud de una conexión, se pierde al reiniciar y no afecta a la otra
# instancia. Las escrituras siempre intentan la primaria.
_replica_pausada_hasta = 0.0
_primaria_pausada_hasta = 0.0


async def leer(request: Request, consulta: Consulta) -> Lectura:
    """
    1. Réplica conectada a la primaria (streaming) o ya promovida -> se lee en la réplica.
    2. Réplica desconectada, pausada o caída -> se lee en la primaria (dato fresco).
       Si está caída, se salta por DB_PAUSA_S segundos (cortacircuito).
    3. Primaria también caída pero la réplica responde -> dato posiblemente viejo,
       avisado con X-Datos-Desactualizados (en un tablón de avisos es mejor que un 503).
    """
    global _replica_pausada_hasta, _primaria_pausada_hasta
    replica: asyncpg.Pool = request.app.state.replica
    primary: asyncpg.Pool = request.app.state.primary

    estado = "caida"
    if time.monotonic() >= _replica_pausada_hasta:
        try:
            async with replica.acquire() as conn:
                estado = clasificar_replica(await conn.fetchrow(ESTADO_REPLICA_SQL))
                if estado in ("streaming", "promovida"):
                    return Lectura(await consulta(conn), "replica", estado)
        except DB_ERRORS as exc:
            _replica_pausada_hasta = time.monotonic() + DB_PAUSA_S
            log.warning("Réplica no disponible: %s. Se lee en la primaria los próximos %.0f s", exc, DB_PAUSA_S)

    if estado == "caida" or time.monotonic() >= _primaria_pausada_hasta:
        log.warning("Réplica en estado '%s': la lectura la atiende la primaria", estado)
        try:
            async with primary.acquire() as conn:
                return Lectura(await consulta(conn), "primary", estado)
        except DB_ERRORS:
            if estado == "caida":
                raise
            _primaria_pausada_hasta = time.monotonic() + DB_PAUSA_S

    log.error("Primaria caída y réplica '%s': entrego datos posiblemente desactualizados", estado)
    async with replica.acquire() as conn:
        return Lectura(await consulta(conn), "replica", estado)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    # Liveness: no consulta la BD para que una caída de PostgreSQL no saque
    # a ambas instancias del balanceador a la vez (falla en cascada).
    return JSONResponse(
        content={"status": "ok", "instance_id": INSTANCE_ID},
        headers={"X-Instance": INSTANCE_ID, "X-DB": "none"},
    )


@app.post("/api/v1/avisos", status_code=status.HTTP_201_CREATED, response_model=Aviso)
async def crear_aviso(aviso: AvisoCreate, request: Request) -> JSONResponse:
    pool: asyncpg.Pool = request.app.state.primary
    async with pool.acquire() as conn:
        fila = await conn.fetchrow(
            f"""
            INSERT INTO avisos (titulo, descripcion, categoria, fecha)
            VALUES ($1, $2, $3, COALESCE($4, now()))
            RETURNING {COLUMNAS}
            """,
            aviso.titulo,
            aviso.descripcion,
            aviso.categoria.value,
            aviso.fecha,
        )
    # Lectura de lo recién escrito: la respuesta trae el aviso completo, así el cliente
    # no necesita volver a pedirlo (la réplica podría no tenerlo todavía).
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder(Aviso(**dict(fila))),
        headers={
            "X-Instance": INSTANCE_ID,
            "X-DB": "primary",
            "Location": f"/api/v1/avisos/{fila['id']}",
        },
    )


@app.get("/api/v1/avisos", response_model=AvisoLista)
async def listar_avisos(
    request: Request,
    categoria: Annotated[Categoria | None, Query(description="Filtrar por categoría")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> JSONResponse:
    cat = categoria.value if categoria else None
    filtro = "fecha >= now() - make_interval(days => $1) AND ($2::varchar IS NULL OR categoria = $2)"

    async def consulta(conn: asyncpg.Connection) -> AvisoLista:
        # Misma transacción (REPEATABLE READ) => total e items son coherentes entre sí.
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            total = await conn.fetchval(f"SELECT count(*) FROM avisos WHERE {filtro}", VIGENCIA_DIAS, cat)
            filas = await conn.fetch(
                f"""
                SELECT {COLUMNAS} FROM avisos
                WHERE {filtro}
                ORDER BY fecha DESC, id DESC
                LIMIT $3 OFFSET $4
                """,
                VIGENCIA_DIAS, cat, limit, offset,
            )
        return AvisoLista(total=total, limit=limit, offset=offset, items=[Aviso(**dict(f)) for f in filas])

    lectura = await leer(request, consulta)
    return JSONResponse(content=jsonable_encoder(lectura.resultado), headers=lectura.cabeceras())


@app.get("/api/v1/avisos/{aviso_id}", response_model=Aviso)
async def detalle_aviso(
    request: Request,
    aviso_id: Annotated[int, Path(ge=1)],
) -> JSONResponse:
    async def consulta(conn: asyncpg.Connection) -> asyncpg.Record | None:
        return await conn.fetchrow(f"SELECT {COLUMNAS} FROM avisos WHERE id = $1", aviso_id)

    lectura = await leer(request, consulta)

    if lectura.resultado is None and lectura.x_db == "replica":
        # Lectura de lo recién escrito: el aviso puede existir en la primaria y aún no
        # haber llegado a la réplica (lag). Antes de responder 404 se confirma en la primaria.
        try:
            async with request.app.state.primary.acquire() as conn:
                fila = await consulta(conn)
            if fila is not None:
                log.info("Aviso %d aún no estaba en la réplica: respondido desde la primaria", aviso_id)
                lectura = Lectura(fila, "primary", lectura.replica_estado)
        except DB_ERRORS as exc:
            log.warning("No se pudo confirmar el 404 en la primaria: %s", exc)

    if lectura.resultado is None:
        raise HTTPException(status_code=404, detail="Aviso no encontrado")
    return JSONResponse(
        content=jsonable_encoder(Aviso(**dict(lectura.resultado))),
        headers=lectura.cabeceras(),
    )


@app.get("/api/v1/replicacion")
async def estado_replicacion(request: Request) -> JSONResponse:
    """Diagnóstico para las pruebas de falla: qué ve cada base en este momento."""
    resultado: dict[str, Any] = {"instance_id": INSTANCE_ID}
    try:
        async with request.app.state.primary.acquire() as conn:
            filas = await conn.fetch(
                """
                SELECT application_name, client_addr::text AS cliente, state,
                       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint AS bytes_pendientes
                FROM pg_stat_replication
                """
            )
            resultado["primary"] = {
                "ok": True,
                "ultimo_id": await conn.fetchval("SELECT max(id) FROM avisos"),
                "replicas_conectadas": [dict(f) for f in filas],
            }
    except DB_ERRORS as exc:
        resultado["primary"] = {"ok": False, "error": type(exc).__name__}
    try:
        async with request.app.state.replica.acquire() as conn:
            estado = await conn.fetchrow(ESTADO_REPLICA_SQL)
            resultado["replica"] = {
                "ok": True,
                "estado": clasificar_replica(estado),
                "ultimo_id": await conn.fetchval("SELECT max(id) FROM avisos"),
            }
    except DB_ERRORS as exc:
        resultado["replica"] = {"ok": False, "error": type(exc).__name__}
    return JSONResponse(
        content=jsonable_encoder(resultado),
        headers={"X-Instance": INSTANCE_ID, "X-DB": "primary+replica"},
    )
