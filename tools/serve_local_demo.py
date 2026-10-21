"""Serve the H5 app, selected public data and API on one localhost origin.

For local demonstration only. Phone access requires the HTTPS reverse proxy in
docs/deployment.md; this server never binds a non-loopback address.
"""

from __future__ import annotations

import argparse
import http.client
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
ASSETS = ROOT / "assets"
DATA = ROOT / "data"


class LocalDemoHandler(BaseHTTPRequestHandler):
    server_version = "MangroveLocalDemo/1.0"

    def _proxy_api(self, method: str) -> None:
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if length < 0 or length > 16 * 1024 * 1024:
            self.send_error(413, "Request too large")
            return
        body = self.rfile.read(length) if method == "POST" else None
        headers = {}
        if method == "POST":
            headers["Content-Type"] = self.headers.get("Content-Type", "application/octet-stream")
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=30)
        try:
            connection.request(method, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            payload = upstream.read()
            self.send_response(upstream.status)
            self.send_header("Content-Type", upstream.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
        except (OSError, http.client.HTTPException):
            self.send_error(502, "Recognition service unavailable")
        finally:
            connection.close()

    def _static_path(self) -> Path | None:
        path = unquote(urlsplit(self.path).path)
        if path in ("/", "/index.html"):
            return FRONTEND / "index.html"
        if path == "/data/sites.json":
            return DATA / "sites.json"
        if path.startswith("/data/species/"):
            relative = path[len("/data/species/"):]
            if relative and "/" not in relative and relative.endswith(".json"):
                return DATA / "species" / relative
        if path.startswith("/assets/"):
            relative = path[len("/assets/"):]
            candidate = (ASSETS / relative).resolve()
            if candidate.is_relative_to(ASSETS.resolve()):
                return candidate
        return None

    def do_GET(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            self._proxy_api("GET")
            return
        path = self._static_path()
        if path is None or not path.is_file():
            self.send_error(404)
            return
        payload = path.read_bytes()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if media_type.startswith("text/") or media_type == "application/json":
            media_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self._proxy_api("POST")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), LocalDemoHandler)
    print(f"本机演示页面：http://127.0.0.1:{args.port}/", flush=True)
    print("API 仅代理到本机 127.0.0.1:8000；Ctrl+C 停止", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
