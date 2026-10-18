"""Bounded comparison: find real CPython syntax rejected beyond tree-sitter's grammar."""
import ast
from harness.repair import parse_python

cases = {
    "assignment-target": "def test_ac1_result():\n    (1 + 2) = 42\n",
    "literal-target": "def test_ac1_result():\n    42 = result()\n",
    "invalid-delete": "def test_ac1_result():\n    del result()\n",
    "invalid-walrus": "def test_ac1_result():\n    assert (result() := 42)\n",
}
for name, source in cases.items():
    grammar_ok, _ = parse_python(source)
    try:
        ast.parse(source)
        ast_error = None
    except SyntaxError as exc:
        ast_error = str(exc)
    print(name, "tree-sitter=", grammar_ok, "CPython AST error=", ast_error)
