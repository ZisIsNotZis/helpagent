"""Grammar conversion (docs/6_ARCHITECTURE.md §4.7): every envelope schema must compile to a
json_schema llama.cpp can turn into a GBNF grammar, and the §0 two-alternative
grammar must be mirrored EXACTLY — the grammar branches on status like the kernel's
validators do (harness/envelopes._grammar_branch; ticket 01 "remaining risk" +
integration evidence: payload-optional grammars let a real 4B emit ok envelopes
missing payload fields, grammar-legal but decode-rejected)."""

import json

from harness.envelopes import SCHEMAS
from harness.model import LlamaServerRunner


def _branches(runner: LlamaServerRunner, step_type: str) -> tuple[dict, dict]:
    js = runner.schema_json(step_type)
    ok_branch, unable_branch = js["anyOf"]
    assert {"ok", "failed", "blocked"} <= set(ok_branch["properties"]["status"]["enum"])
    assert unable_branch["properties"]["status"] == {"const": "unable"}
    return ok_branch, unable_branch


def test_every_schema_compiles_to_the_two_branch_grammar():
    runner = LlamaServerRunner()
    for step_type in SCHEMAS:
        js = runner.schema_json(step_type)  # second call hits the cache
        assert json.dumps(js)  # payload-able for the HTTP body
        ok_branch, unable_branch = js["anyOf"]
        assert ok_branch["properties"]["status"]["enum"] == ["ok", "failed", "blocked"]
        assert unable_branch["properties"]["status"] == {"const": "unable"}
        for branch in (ok_branch, unable_branch):
            assert branch["additionalProperties"] is False  # closed grammar (extra="forbid")


def test_ok_branch_requires_payload_forbids_unable_reason():
    ok_branch, _ = _branches(LlamaServerRunner(), "write_test")
    assert "content" in ok_branch["required"] and "file_path" in ok_branch["required"]
    assert "unable_reason" not in ok_branch["properties"]       # forbidden unless unable
    assert "comment" in ok_branch["required"]                   # mandatory self-summary


def test_unable_branch_requires_reason_forbids_payload():
    _, unable_branch = _branches(LlamaServerRunner(), "write_test")
    assert set(unable_branch["required"]) == {"status", "comment", "unable_reason"}
    payload = set(unable_branch["properties"]) - {"status", "comment", "unable_reason"}
    assert payload == set()  # payload fields absent entirely → illegal on this branch


def test_unable_alternative_exists_for_every_step_type():
    runner = LlamaServerRunner()
    for step_type in SCHEMAS:
        _, unable_branch = _branches(runner, step_type)
        assert unable_branch["required"] == sorted({"status", "comment", "unable_reason"})


def test_nested_defs_are_carried_for_expand():
    js = LlamaServerRunner().schema_json("expand")
    ok_branch, _ = js["anyOf"]
    assert "children" in ok_branch["required"]
    assert "$defs" in js  # ChildFill refs stay resolvable for the GBNF converter
    assert json.dumps(ok_branch["properties"]["children"]).count("$ref") >= 1
