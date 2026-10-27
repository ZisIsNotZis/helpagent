"""Parse-on-arrival + one bounded repair respawn (docs/6_ARCHITECTURE.md §4.7 Model Interface).

"Post-generation parse with tree-sitter immediately; trivial syntax errors
auto-repaired, otherwise step respawned with only the broken excerpt."

Minimal M1 reading (DECISION): a parse failure triggers exactly ONE respawn whose
input is the bounded excerpt around the first tree-sitter error (+ ground truth) —
not the failed attempt's full output. This is §4.7's specific rule for parse
failures; the general erasure rule (§2.4a "never the failed attempt's text") still
governs everything else: the envelope comment and all content outside the excerpt
stay erased, the ledger retains the full failed text (§2.4b), and if the content
still does not parse after the respawn the step raises SchemaViolation and the
ordinary erasure path takes over.

Wired into ``runner.llm_step`` for CONTENT_STEPS only (write_test — the only
content-emitting schema left, docs/7_ENVELOPES.md §24), after schema validation,
before the envelope is returned.
"""

from __future__ import annotations

from typing import Any

import tree_sitter_python
from tree_sitter import Language, Parser

from harness.runner import FailureSummary, SchemaViolation, llm_step, note

_PARSER = Parser(Language(tree_sitter_python.language()))

EXCERPT_RADIUS = 5  # lines of context around the first error node (§4.7 "broken excerpt")


def parse_python(source: str) -> tuple[bool, Any]:
    """Tree-sitter parse. Returns (ok, first_error_node_or_None)."""
    tree = _PARSER.parse(source.encode())
    root = tree.root_node
    if not root.has_error:
        return True, None

    def _first_error(node: Any) -> Any:
        if node.type == "ERROR" or node.is_missing:
            return node
        for child in node.children:
            found = _first_error(child)
            if found is not None:
                return found
        return None

    return False, _first_error(root)


def broken_excerpt(source: str, error_node: Any, radius: int = EXCERPT_RADIUS) -> str:
    """The bounded broken region: ±``radius`` lines around the first error, numbered."""
    lines = source.splitlines()
    row = error_node.start_point[0] if error_node is not None else 0
    lo = max(0, row - radius)
    hi = min(len(lines), row + radius + 1)
    numbered = [f"{i + 1:4d} | {lines[i]}" for i in range(lo, hi)]
    marker_row = row - lo
    if 0 <= marker_row < len(numbered):
        numbered[marker_row] += "   <-- first parse error here"
    return "\n".join(numbered)


async def repair_code(
    source: str,
    model: Any,
    step_type: str,
    question: str,
    context: dict[str, Any] | None = None,
    ground_truth: dict[str, str] | None = None,
) -> str:
    """Parse; on failure ONE respawn with the broken excerpt; re-parse; still broken
    ⇒ SchemaViolation. Returns the (possibly repaired) source on success."""
    ok, node = parse_python(source)
    if ok:
        return source

    note("repair_attempted", step_type=step_type)
    excerpt = broken_excerpt(source, node)
    env = await llm_step(
        model,
        step_type,
        artifacts={
            "broken_excerpt": excerpt,
            "parse_error": f"tree-sitter reports a syntax error at line {node.start_point[0] + 1}",
            **(ground_truth or {}),
        },
        question=(
            f"The previous {step_type} output failed to parse. Return the COMPLETE corrected "
            f"file in the content field — same purpose as the original request: {question}"
        ),
        failure=FailureSummary(
            step_type=step_type,
            summary=f"{step_type}: content has a Python syntax error at line {node.start_point[0] + 1}; "
                    "return the complete corrected file.",
            missing=["parse-clean content"],
        ),
        context=context,
        repair=False,  # a respawn never recurses into repair (§4.7: ONE bounded respawn)
    )
    repaired = env.content
    ok2, node2 = parse_python(repaired)
    if not ok2:
        note("repair_failed", step_type=step_type)
        raise SchemaViolation(
            f"{step_type}: content still fails to parse after one repair respawn "
            f"(line {node2.start_point[0] + 1}) — attempt erased, failure summary only"
        )
    note("repair_ok", step_type=step_type)
    return repaired
