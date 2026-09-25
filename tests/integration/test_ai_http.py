"""The real HTTP code paths of both AI providers, against a local stub server.

No real AI service is contacted: a tiny HTTP server on 127.0.0.1 records each
request and returns canned responses in the shape the real APIs use.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.core.models import Category


class _Stub:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append({"path": self.path, "headers": dict(self.headers),
                                      "body": body})
                status, payload = stub.responses.pop(0)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def stub():
    servers = []

    def make(responses):
        s = _Stub(responses)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def _claude_message(text, stop_reason="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop_reason,
            "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_claude_sdk_request_shape(stub, monkeypatch):
    import anthropic

    from app.llm import provider as p

    server = stub([(200, _claude_message(
        '{"category": "graphics", "restated_problem": "GPU lag.", '
        '"checks": ["get_gpu_usage"], "reasoning": "Check GPU load."}'))])
    claude = p.AnthropicProvider(endpoint="https://api.anthropic.com", model="claude-opus-5",
                                 api_key="sk-ant-test")
    monkeypatch.setattr(claude, "_client", lambda: anthropic.Anthropic(
        api_key="sk-ant-test", base_url=server.url, max_retries=0))
    understood = claude.understand("my gpu is laggy", ["get_gpu_usage", "get_cpu_usage"])
    assert understood.category == Category.GRAPHICS
    assert understood.checks == ["get_gpu_usage"]
    request = server.requests[0]
    assert request["path"].startswith("/v1/messages")
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["x-api-key"] == "sk-ant-test"
    assert "server-side-fallback-2026-07-01" in headers["anthropic-beta"]
    body = request["body"]
    assert body["model"] == "claude-opus-5"
    assert body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "my gpu is laggy" in body["messages"][0]["content"]


def test_claude_http_errors_become_friendly_messages(stub, monkeypatch):
    import anthropic

    from app.llm import provider as p

    server = stub([(401, {"type": "error", "error": {"type": "authentication_error",
                                                     "message": "invalid x-api-key"}})])
    claude = p.AnthropicProvider(endpoint="https://api.anthropic.com", model="claude-opus-5",
                                 api_key="sk-ant-bad")
    monkeypatch.setattr(claude, "_client", lambda: anthropic.Anthropic(
        api_key="sk-ant-bad", base_url=server.url, max_retries=0))
    ok, message = claude.test_connection()
    assert not ok and message == "The provider rejected the API key."


def test_openai_compatible_structured_output_and_plain_retry(stub):
    from app.llm.provider import OpenAICompatibleProvider

    answer = {"choices": [{"message": {"content": '{"enough_evidence": true, '
                                                  '"next_checks": [], "reasoning": "Done."}'}}]}
    server = stub([(400, {"error": "response_format not supported"}), (200, answer)])
    local = OpenAICompatibleProvider(endpoint=server.url + "/v1", model="llama3.1",
                                     api_key=None)
    assert local.on_this_pc and local.available
    data = local._json("system", "user", {"type": "object"})
    assert data["enough_evidence"] is True
    first, second = server.requests
    assert first["path"] == "/v1/chat/completions"
    assert first["body"]["response_format"]["type"] == "json_schema"
    assert "authorization" not in {k.lower() for k in first["headers"]}  # keyless local AI
    assert "response_format" not in second["body"]
    assert "JSON object" in second["body"]["messages"][0]["content"]
