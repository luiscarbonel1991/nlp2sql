"""A local stand-in for the OpenAI HTTP API.

The real OpenAI SDK talks to it through ``OPENAI_BASE_URL``, so tests exercise the
library exactly as a user would (SDK, adapters, prompts) without keys or cost, and can
inspect every request the library sends.

- ``/v1/chat/completions`` answers SQL generation with ``{"sql": fake.sql, ...}`` and
  SQL validation with ``{"is_valid": true, ...}``.
- ``/v1/embeddings`` returns deterministic bag-of-words vectors (feature hashing), so
  word overlap between a question and a table description gives real similarity.
"""

import hashlib
import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

EMBEDDING_DIMENSION = 1536
VALIDATION_SYSTEM_PREFIX = "You are a SQL validation expert"


def _embed(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % EMBEDDING_DIMENSION] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


@dataclass
class FakeOpenAI:
    """Configure ``sql`` (and optionally ``chat_status``) before each call; read ``requests``."""

    sql: str = "SELECT COUNT(*) AS user_count FROM users;"
    chat_status: Optional[int] = None
    requests: list[dict[str, Any]] = field(default_factory=list)
    _server: Optional[ThreadingHTTPServer] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def calls(self, kind: str) -> int:
        return sum(1 for request in self.requests if request["kind"] == kind)

    def start(self) -> "FakeOpenAI":
        fake = self

        class Handler(BaseHTTPRequestHandler):
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
                if self.path.endswith("/embeddings"):
                    inputs = body.get("input")
                    inputs = [inputs] if isinstance(inputs, str) else inputs
                    fake._record({"kind": "embedding", "inputs": len(inputs)})
                    return self._send(
                        200,
                        {
                            "object": "list",
                            "data": [
                                {"object": "embedding", "index": i, "embedding": _embed(text)}
                                for i, text in enumerate(inputs)
                            ],
                            "model": body.get("model"),
                            "usage": {"prompt_tokens": 1, "total_tokens": 1},
                        },
                    )
                if self.path.endswith("/chat/completions"):
                    return self._chat(body)
                return self._send(404, {"error": {"message": f"not faked: {self.path}"}})

            def _chat(self, body: dict[str, Any]) -> None:
                messages = body.get("messages", [])
                system = next((m["content"] for m in messages if m["role"] == "system"), "")
                user = next((m["content"] for m in messages if m["role"] == "user"), "")
                kind = "validate" if system.startswith(VALIDATION_SYSTEM_PREFIX) else "generate"
                fake._record({"kind": kind, "body": body, "prompt": user})
                if fake.chat_status:
                    return self._send(
                        fake.chat_status,
                        {"error": {"message": f"fake {fake.chat_status}", "type": "invalid_request_error"}},
                    )
                if kind == "validate":
                    content = json.dumps({"is_valid": True, "errors": [], "warnings": [], "suggestions": []})
                else:
                    content = json.dumps({"sql": fake.sql, "explanation": "fake", "confidence": 0.9})
                usage = {"prompt_tokens": (len(system) + len(user)) // 4, "completion_tokens": len(content) // 4}
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                return self._send(
                    200,
                    {
                        "id": f"chatcmpl-fake-{len(fake.requests)}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": body.get("model"),
                        "choices": [
                            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                        ],
                        "usage": usage,
                    },
                )

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def _record(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self.requests.append(entry)
