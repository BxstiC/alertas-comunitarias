import hmac
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# Una API key por tipo de cliente. Traefik cuenta el límite de peticiones por API key,
# así cada cliente tiene su propio límite y se puede revocar a uno sin tocar a los otros.
CLIENTES = {
    "web": os.environ.get("API_KEY", ""),
    "movil": os.environ.get("API_KEY_MOVIL", ""),
    "municipio": os.environ.get("API_KEY_MUNICIPIO", ""),
}

for nombre, clave in CLIENTES.items():
    if len(clave) < 24:
        raise RuntimeError(f"La API key del cliente '{nombre}' debe tener al menos 24 caracteres")
if len(set(CLIENTES.values())) != len(CLIENTES):
    raise RuntimeError("Cada cliente debe tener una API key distinta")


def cliente_de(clave_recibida: str) -> str | None:
    """Devuelve el nombre del cliente dueño de la clave, o None si no es válida."""
    encontrado = None
    # Se compara contra TODAS las claves (sin salir antes) y en tiempo constante,
    # para no filtrar por el tiempo de respuesta cuál clave se parece a la recibida.
    for nombre, clave in CLIENTES.items():
        if hmac.compare_digest(clave_recibida.encode(), clave.encode()):
            encontrado = nombre
    return encontrado


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if self.path != "/verify":
            self.send_error(404)
            return

        cliente = cliente_de(self.headers.get("X-API-Key", ""))
        if cliente is None:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"API key required or invalid")
            return

        # Traefik copia X-Cliente a la petición que sigue hacia el balanceador (authResponseHeaders).
        self.send_response(200)
        self.send_header("X-Cliente", cliente)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        if self.path == "/health":
            return
        super().log_message(format, *args)


ThreadingHTTPServer(("0.0.0.0", 8080), AuthHandler).serve_forever()
