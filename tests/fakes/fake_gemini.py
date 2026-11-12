"""A local stand-in for the Gemini Developer API (``generateContent``).

The real ``google-genai`` SDK talks to it through ``GOOGLE_GEMINI_BASE_URL``, so tests
exercise the adapter exactly as a user would (SDK, request body, API version in the
URL) without keys or cost, and can inspect every request the library sends.

- ``POST /{version}/models/{model}:generateContent`` answers SQL generation with
  ``{"sql": fake.sql, ...}`` and SQL validation with ``{"is_valid": true, ...}``.
  ``contents`` queues raw answers for the next generation calls (malformed output),
  ``finish_reason`` sets how they end, ``status`` makes every call fail with that code.
- Usage reports prompt, answer and thinking tokens (``thoughts_tokens``), so token
  accounting can be checked.
"""

import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

VALIDATION_PREFIX = "Validate this SQL query"
_PATH = re.compile(r"^/(?P<version>[^/]+)/models/(?P<model>[^:]+):generateContent$")


@dataclass
class FakeGemini:
    """Configure ``sql`` (and optionally ``status``) before each call; read ``requests``."""

    sql: str = "SELECT COUNT(*) AS user_count FROM users;"
    status: Optional[int] = None
    error_body: Optional[dict[str, Any]] = None
    contents: list[str] = field(default_factory=list)
    validation_content: str | None = None
    finish_reason: str = "STOP"
    thoughts_tokens: int = 7
    requests: list[dict[str, Any]] = field(default_factory=list)
    _server: Optional[ThreadingHTTPServer] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def calls(self, kind: str) -> int:
        return sum(1 for request in self.requests if request["kind"] == kind)

    def last(self, kind: str = "generate") -> dict[str, Any]:
        return [request for request in self.requests if request["kind"] == kind][-1]

    def start(self) -> "FakeGemini":
        fake = self

        class Handler(BaseHTTPRequestHandler):
            # Keep-alive, like the real API: the SDK reuses pooled connections
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                pass

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802 (http.server naming)
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                match = _PATH.match(self.path.split("?")[0])
                if not match:
                    return self._send(404, {"error": {"code": 404, "message": f"not faked: {self.path}"}})
                prompt = "".join(
                    part.get("text", "") for content in body.get("contents", []) for part in content.get("parts", [])
                )
                kind = "validate" if prompt.startswith(VALIDATION_PREFIX) else "generate"
                entry = {
                    "kind": kind,
                    "version": match["version"],
                    "model": match["model"],
                    "body": body,
                    "prompt": prompt,
                    "api_key": self.headers.get("x-goog-api-key"),
                }
                if fake.status:
                    fake._record(entry)
                    error = fake.error_body or {
                        "error": {"code": fake.status, "message": f"fake {fake.status}", "status": "FAKE"}
                    }
                    return self._send(fake.status, error)
                finish_reason = "STOP"
                if kind == "validate":
                    text = fake.validation_content
                    if text is None:
                        text = json.dumps({"is_valid": True, "issues": [], "suggestions": [], "complexity": "simple"})
                else:
                    text = fake._next_generation_content()
                    finish_reason = fake.finish_reason
                system = "".join(part.get("text", "") for part in body.get("systemInstruction", {}).get("parts", []))
                usage = {
                    "promptTokenCount": (len(system) + len(prompt)) // 4,
                    "candidatesTokenCount": len(text) // 4,
                    "thoughtsTokenCount": fake.thoughts_tokens,
                }
                usage["totalTokenCount"] = sum(usage.values())
                entry["usage"] = usage
                fake._record(entry)
                candidate: dict[str, Any] = {"finishReason": finish_reason, "index": 0}
                if text:
                    candidate["content"] = {"role": "model", "parts": [{"text": text}]}
                return self._send(
                    200, {"candidates": [candidate], "usageMetadata": usage, "modelVersion": match["model"]}
                )

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def _next_generation_content(self) -> str:
        with self._lock:
            if self.contents:
                return self.contents.pop(0)
        return json.dumps({"sql": self.sql, "explanation": "fake", "confidence": 0.9})

    def _record(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self.requests.append(entry)
