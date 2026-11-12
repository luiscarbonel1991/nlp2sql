"""A local stand-in for the Anthropic Messages API.

The real ``anthropic`` SDK talks to it through ``ANTHROPIC_BASE_URL``, so tests exercise
the adapter exactly as a user would (SDK, request body) without keys or cost, and can
inspect every request the library sends.

- ``POST /v1/messages`` answers SQL generation with ``{"sql": fake.sql, ...}`` and SQL
  validation with ``{"is_valid": true, ...}``.
"""

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

VALIDATION_SYSTEM_PREFIX = "You are a SQL validation expert"


class _Server(ThreadingHTTPServer):
    # Room for a burst of concurrent connections; the default backlog of 5 resets the rest
    request_queue_size = 64


@dataclass
class FakeAnthropic:
    """Configure ``sql`` before each call; read ``requests``."""

    sql: str = "SELECT COUNT(*) AS user_count FROM users;"
    requests: list[dict[str, Any]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def calls(self, kind: str) -> int:
        return sum(1 for request in self.requests if request["kind"] == kind)

    def start(self) -> "FakeAnthropic":
        fake = self

        class Handler(BaseHTTPRequestHandler):
            # Keep-alive, like the real API: the SDK reuses pooled connections
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:
                pass

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if not self.path.endswith("/v1/messages"):
                    return self._send(
                        404, {"type": "error", "error": {"type": "not_found_error", "message": self.path}}
                    )
                system = body.get("system") or ""
                kind = "validate" if system.startswith(VALIDATION_SYSTEM_PREFIX) else "generate"
                if kind == "validate":
                    text = json.dumps({"is_valid": True, "errors": [], "warnings": [], "suggestions": []})
                else:
                    text = json.dumps({"sql": fake.sql, "explanation": "Counts users.", "confidence": 0.9})
                with fake._lock:
                    fake.requests.append({"kind": kind, "body": body})
                return self._send(
                    200,
                    {
                        "id": f"msg_fake_{len(fake.requests)}",
                        "type": "message",
                        "role": "assistant",
                        "model": body.get("model"),
                        "content": [{"type": "text", "text": text}],
                        "stop_reason": "end_turn",
                        "stop_sequence": None,
                        "usage": {"input_tokens": len(json.dumps(body)) // 4, "output_tokens": len(text) // 4},
                    },
                )

        self._server = _Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
