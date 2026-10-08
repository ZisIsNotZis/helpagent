"""LlamaServerRunner — the real model runner (DESIGN §4.7 Model Interface, §8 M1).

Protocol parity with FakeModelRunner: ``async complete(request)``
returns the *raw decoded output* — here, the envelope JSON string exactly as the
server produced it — and deliberately does NOT schema-validate: validation is the
kernel's invariant, enforced by ``harness.runner.llm_step``.
Scripts cannot tell fake and real apart.

§0 grammar → json_schema alignment: the kernel's ``Envelope._grammar_branch`` has
exactly two alternatives — (1) status ∈ {ok, failed, blocked}: payload fields
REQUIRED, ``unable_reason`` forbidden; (2) status == unable: ``unable_reason``
REQUIRED, payload fields forbidden. ``schema_json`` mirrors that rule one-to-one as
an ``anyOf`` of the two branch objects (const/enum status discriminator, each branch
closed via ``additionalProperties: false``, payload fields absent from the unable
branch's properties entirely). This is the alignment the kernel report demanded
(ticket 01 "remaining risk"): the grammar and the validators branch identically.
Integration evidence (this ticket): the simpler "fields optional + validators
enforce" mapping let a real 4B emit an ok envelope missing ``file_path`` — grammar-legal,
decode-rejected — so the branch rule was moved INTO the grammar, where §0 always
said it belongs ("the ok branch requires the payload fields"). The REQUIRED-sentinel
validators remain the decode-time backstop and violation messages stay aligned.

Metrics: llama.cpp reports token usage and KV-cache timings per call
(``usage.prompt_tokens/completion_tokens``, ``timings.cache_n/prompt_n``). They are
exposed as ``last_metrics`` (most recent call) / ``last_metrics_list`` (one entry per
call of the last ``complete_n``) and folded into the kernel's ``llm_invocation``
ledger note by llm_step — counters only, never content (KERNEL_API §5).
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
import warnings
from typing import Any

from pydantic.json_schema import PydanticJsonSchemaWarning

from harness.envelopes import SCHEMAS

DEFAULT_BASE_URL = "http://127.0.0.1:8833"
MAX_TOKENS = 3000  # the 3k output ceiling (ENVELOPE_SCHEMAS §24)
TRANSPORT_ATTEMPTS = 2  # DESIGN §4.7: cheap retries are a local-GPU property


class TransportError(Exception):
    """The model server could not be reached after the transport retries. Infra
    failure — distinctly NOT a SchemaViolation (nothing was erased; nothing to erase)."""


def _http_post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Module-level so tests can monkeypatch the transport (urllib, stdlib only)."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _http_get_json(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


BASE_FIELDS = ("status", "comment", "unable_reason")


class LlamaServerRunner:
    """Async facade over llama.cpp's OpenAI-compatible endpoint. Same protocol as
    FakeModelRunner: ``async complete(request) -> str`` (the envelope JSON text)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "helpagent",
        temperature: float = 0.2,
        timeout_s: float = 180.0,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.last_metrics: dict[str, Any] | None = None
        self.last_metrics_list: list[dict[str, Any]] = []
        self._schema_cache: dict[str, dict[str, Any]] = {}

    # -- grammar ----------------------------------------------------------

    def schema_json(self, step_type: str) -> dict[str, Any]:
        """The §0 two-branch grammar for the step's envelope (cached; see the module
        docstring for the alignment rationale). Raises KeyError for unknown step
        types — the same programmer-error contract as runner.schema_for_step."""
        if step_type not in self._schema_cache:
            self._schema_cache[step_type] = self._branch_grammar(step_type)
        return self._schema_cache[step_type]

    @staticmethod
    def _branch_grammar(step_type: str) -> dict[str, Any]:
        model = SCHEMAS["judge_aspect"] if step_type.startswith("judge_") else SCHEMAS[step_type]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=PydanticJsonSchemaWarning)
            js = model.model_json_schema()
        props = dict(js.get("properties", {}))
        required = set(js.get("required", []))
        payload = [f for f in props if f not in BASE_FIELDS]

        # branch 1 — status ∈ {ok, failed, blocked}: payload REQUIRED, unable_reason forbidden
        ok_props = {f: props[f] for f in props if f != "unable_reason"}
        ok_props["status"] = {"enum": ["ok", "failed", "blocked"]}
        ok_branch = {
            "type": "object",
            "properties": ok_props,
            "required": sorted((required | set(payload)) - {"unable_reason"}),
            "additionalProperties": False,
        }
        # branch 2 — status == unable: unable_reason REQUIRED, payload FORBIDDEN
        # (absent from properties entirely; the closed object makes any payload key illegal)
        unable_branch = {
            "type": "object",
            "properties": {
                "status": {"const": "unable"},
                "comment": props.get("comment", {"type": "string"}),
                "unable_reason": props.get("unable_reason", {"type": "string"}),
            },
            "required": sorted({"status", "comment", "unable_reason"}),
            "additionalProperties": False,
        }
        grammar: dict[str, Any] = {"anyOf": [ok_branch, unable_branch]}
        if js.get("$defs"):
            grammar["$defs"] = js["$defs"]  # nested models (e.g. expand.children) keep their refs
        return grammar

    # -- health -----------------------------------------------------------

    def health_check(self) -> bool:
        try:
            data = _http_get_json(f"{self.base_url}/health", timeout=min(self.timeout_s, 5.0))
            return data.get("status") == "ok"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return False

    # -- invocation -------------------------------------------------------

    def _payload(self, request: Any) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            # thinking preambles burn the budget and empty the content (ticket 01)
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": request.step_type, "schema": self.schema_json(request.step_type)},
            },
        }

    @staticmethod
    def _metrics(data: dict[str, Any]) -> dict[str, Any]:
        usage = data.get("usage") or {}
        timings = data.get("timings") or {}
        prompt_n = int(timings.get("prompt_n") or usage.get("prompt_tokens") or 0)
        cache_n = int(timings.get("cache_n") or 0)
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "cache_n": cache_n,
            "prompt_n": prompt_n,
            # KV-cache reuse rate over the prompt (DESIGN §9.11 measured dimension)
            "cache_hit": round(cache_n / prompt_n, 4) if prompt_n else 0.0,
        }

    async def complete(self, request: Any) -> str:
        """One model call with transport retry (2 attempts). Returns the envelope
        JSON string; raises TransportError when the server is unreachable."""
        payload = self._payload(request)
        last_exc: Exception | None = None
        for attempt in range(1, TRANSPORT_ATTEMPTS + 1):
            try:
                started = time.monotonic()
                data = await asyncio.to_thread(
                    _http_post_json, f"{self.base_url}/v1/chat/completions", payload, self.timeout_s
                )
                content = data["choices"][0]["message"]["content"]
                metrics = self._metrics(data)
                metrics["wall_model_s"] = round(time.monotonic() - started, 3)
                self.last_metrics = metrics
                self.last_metrics_list = [metrics]
                return content
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_exc = exc
                if attempt < TRANSPORT_ATTEMPTS:
                    await asyncio.sleep(0.5 * attempt)
        raise TransportError(
            f"llama-server unreachable after {TRANSPORT_ATTEMPTS} attempts: {last_exc!r}"
        ) from last_exc

    async def complete_n(self, request: Any, n: int) -> list[str]:
        """N raw candidates for best-of-N (DESIGN §4.7: sample 3–5, deterministic
        checker selects). Sequential on purpose — one local GPU, one slot; parallel
        peers thrash the KV cache (DESIGN §4.1 cache note)."""
        outs: list[str] = []
        for _ in range(max(1, n)):
            outs.append(await self.complete(request))
        return outs
