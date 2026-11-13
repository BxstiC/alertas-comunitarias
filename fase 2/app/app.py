"""
Servicio de Alertas Comunitarias Vecinales.

- Escrituras  -> base de datos PRIMARIA (cabecera X-DB: primary).
- Lecturas    -> RÉPLICA por streaming (cabecera X-DB: replica).
- Todas las respuestas llevan X-Instance con el valor de INSTANCE_ID.
- Stateless: no se guarda nada en memoria ni en disco; todo vive en PostgreSQL.
  (Los pools de conexiones no son estado de negocio: se recrean al reiniciar.)
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, AsyncIterator

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
async def crear_pool(dsn: str, nombre: str, solo_lectura: bool) -> asyncpg.Pool:
    server_settings = {"application_name": f"avisos-{INSTANCE_ID}-{nombre}"}
    if solo_lectura:
        # Defensa adicional: aunque la réplica ya es read-only, el pool también lo es.
        server_settings["default_transaction_read_only"] = "on"

    for intento in range(1, DB_CONNECT_RETRIES + 1):
        try:
            pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=DB_POOL_MIN,
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
        app.state.replica = await crear_pool(DB_REPLICA_URL, "replica", solo_lectura=True)
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

        async def send_con_cabecera(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-instance"]
                headers.append((b"x-instance", INSTANCE_ID.encode("latin-1")))
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
# Endpoints
# ---------------------------------------------------------------------------
COLUMNAS = "id, titulo, descripcion, categoria, fecha"


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
    pool: asyncpg.Pool = request.app.state.replica
    cat = categoria.value if categoria else None
    filtro = "fecha >= now() - make_interval(days => $1) AND ($2::varchar IS NULL OR categoria = $2)"

    async with pool.acquire() as conn:
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

    cuerpo = AvisoLista(
        total=total, limit=limit, offset=offset, items=[Aviso(**dict(f)) for f in filas]
    )
    return JSONResponse(
        content=jsonable_encoder(cuerpo),
        headers={"X-Instance": INSTANCE_ID, "X-DB": "replica"},
    )


@app.get("/api/v1/avisos/{aviso_id}", response_model=Aviso)
async def detalle_aviso(
    request: Request,
    aviso_id: Annotated[int, Path(ge=1)],
) -> JSONResponse:
    pool: asyncpg.Pool = request.app.state.replica
    async with pool.acquire() as conn:
        fila = await conn.fetchrow(f"SELECT {COLUMNAS} FROM avisos WHERE id = $1", aviso_id)
    if fila is None:
        # Puede ocurrir brevemente justo tras un POST por el lag de replicación.
        raise HTTPException(status_code=404, detail="Aviso no encontrado")
    return JSONResponse(
        content=jsonable_encoder(Aviso(**dict(fila))),
        headers={"X-Instance": INSTANCE_ID, "X-DB": "replica"},
    )
