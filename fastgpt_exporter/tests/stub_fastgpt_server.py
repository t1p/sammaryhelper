"""Минимальный локальный стаб FastGPT API (только stdlib) для тестов.

Реализует ровно те 4 эндпоинта, которые использует fastgpt_client.py, и
пишет журнал вызовов, чтобы тесты могли проверять, что и сколько раз
было вызвано — без обращения к реальному инстансу FastGPT.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class StubFastGPTServer:
    def __init__(self):
        self.calls: list[dict] = []
        self._dataset_counter = 0
        self._collection_counter = 0
        self.fail_delete = False
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        assert self._httpd is not None
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def start(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _read_body(self) -> dict:
                length = int(self.headers.get("Content-Length", 0))
                if not length:
                    return {}
                return json.loads(self.rfile.read(length) or b"{}")

            def _reply(self, status: int, payload: dict):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                parsed = urlparse(self.path)
                body = self._read_body()
                server.calls.append({"method": "POST", "path": parsed.path, "body": body})

                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    self._reply(401, {"code": 401, "message": "missing api key"})
                    return

                if parsed.path == "/api/core/dataset/create":
                    server._dataset_counter += 1
                    self._reply(200, {"data": f"ds_{server._dataset_counter}"})
                elif parsed.path == "/api/core/dataset/collection/create":
                    server._collection_counter += 1
                    self._reply(200, {"data": {"collectionId": f"col_{server._collection_counter}"}})
                elif parsed.path == "/api/core/dataset/data/pushData":
                    data = body.get("data", [])
                    if len(data) > 200:
                        self._reply(400, {"code": 400, "message": "too many items"})
                        return
                    self._reply(200, {"data": {"insertLen": len(data)}})
                else:
                    self._reply(404, {"code": 404, "message": "not found"})

            def do_DELETE(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                server.calls.append({"method": "DELETE", "path": parsed.path, "query": query})
                if server.fail_delete:
                    self._reply(500, {"code": 500, "message": "simulated failure"})
                else:
                    self._reply(200, {"data": True})

            def do_GET(self):
                parsed = urlparse(self.path)
                server.calls.append({"method": "GET", "path": parsed.path})
                if parsed.path == "/api/core/dataset/training/getDatasetTrainingQueue":
                    self._reply(200, {"data": {"rebuildingCount": 0, "trainingCount": 0}})
                else:
                    self._reply(404, {"code": 404, "message": "not found"})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def calls_to(self, path: str) -> list[dict]:
        return [c for c in self.calls if c["path"] == path]
