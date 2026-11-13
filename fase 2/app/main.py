import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

instance_id = os.environ["INSTANCE_ID"]
db_primary_url = os.environ["DB_PRIMARY_URL"]
db_replica_url = os.environ["DB_REPLICA_URL"]

app = FastAPI(title="Servicio temporal de avisos")
app.state.instance_id = instance_id
app.state.db_primary_url = db_primary_url
app.state.db_replica_url = db_replica_url


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        content={"status": "ok", "instance_id": app.state.instance_id},
        headers={"X-Instance": app.state.instance_id},
    )


@app.get("/api/v1/avisos")
def listar_avisos() -> JSONResponse:
    return JSONResponse(
        content={"message": "Endpoint temporal; lógica de negocio pendiente"},
        headers={"X-Instance": app.state.instance_id, "X-DB": "replica"},
    )


@app.post("/api/v1/avisos")
def crear_aviso() -> JSONResponse:
    return JSONResponse(
        content={"message": "Endpoint temporal; lógica de negocio pendiente"},
        headers={"X-Instance": app.state.instance_id, "X-DB": "primary"},
    )
