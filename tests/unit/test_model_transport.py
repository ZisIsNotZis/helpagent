"""LlamaServerRunner transport behavior with the real HTTP layer monkeypatched
(stdlib urllib behind harness.model._http_post_json — the patchable seam)."""

import asyncio
import json
import urllib.error

import pytest

from harness.model import TransportError, LlamaServerRunner
from harness.runner import LLMRequest, compose_prompt


def _request() -> LLMRequest:
    return LLMRequest(step_type="write_test", artifacts={}, question="q",
                      tools=[], fresh=False, prompt=compose_prompt("write_test", {}, "q"))


GOOD = {
    "choices": [{"message": {"content": json.dumps({
        "status": "ok", "comment": "c", "file_path": "tests/test_x.py", "content": "x = 1\n"})}}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 50},
    "timings": {"cache_n": 800, "prompt_n": 1000},
}


def test_transport_retry_then_success(monkeypatch):
    calls: list[str] = []

    def flaky(url, payload, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.URLError("connection reset")
        return GOOD

    monkeypatch.setattr("harness.model._http_post_json", flaky)
    runner = LlamaServerRunner()
    out = asyncio.run(runner.complete(_request()))
    assert isinstance(out, str) and json.loads(out)["status"] == "ok"
    assert len(calls) == 2  # TRANSPORT_ATTEMPTS
    assert runner.last_metrics["cache_hit"] == 0.8
    assert runner.last_metrics["prompt_tokens"] == 1000
    assert runner.last_metrics["completion_tokens"] == 50


def test_transport_exhaustion_raises_transport_error(monkeypatch):
    calls: list[str] = []

    def dead(url, payload, timeout):
        calls.append(url)
        raise urllib.error.URLError("server down")

    monkeypatch.setattr("harness.model._http_post_json", dead)
    runner = LlamaServerRunner()
    with pytest.raises(TransportError, match="unreachable after 2 attempts"):
        asyncio.run(runner.complete(_request()))
    assert len(calls) == 2


def test_payload_carries_grammar_and_disables_thinking(monkeypatch):
    seen: dict = {}

    def capture(url, payload, timeout):
        seen.update(payload)
        return GOOD

    monkeypatch.setattr("harness.model._http_post_json", capture)
    asyncio.run(LlamaServerRunner().complete(_request()))
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}  # ticket 01 gotcha
    assert seen["temperature"] == 0.2
    rf = seen["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "write_test"
    ok_branch, unable_branch = rf["json_schema"]["schema"]["anyOf"]
    assert ok_branch["additionalProperties"] is False and unable_branch["additionalProperties"] is False
    assert "content" in ok_branch["properties"]


def test_health_check_true_and_false(monkeypatch):
    monkeypatch.setattr("harness.model._http_get_json", lambda url, timeout: {"status": "ok"})
    assert LlamaServerRunner().health_check() is True

    def down(url, timeout):
        raise urllib.error.URLError("no server")

    monkeypatch.setattr("harness.model._http_get_json", down)
    assert LlamaServerRunner().health_check() is False
