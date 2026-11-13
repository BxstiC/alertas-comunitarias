import hmac
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


api_key = os.environ.get("API_KEY", "")
if len(api_key) < 24:
    raise RuntimeError("API_KEY debe tener al menos 24 caracteres")


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

        provided_key = self.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided_key, api_key):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"API key required or invalid")
            return

        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        if self.path == "/health":
            return
        super().log_message(format, *args)


ThreadingHTTPServer(("0.0.0.0", 8080), AuthHandler).serve_forever()
