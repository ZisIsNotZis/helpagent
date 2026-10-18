"""Lexer contract tests."""

import pytest

from tok.lexer import LexError, tokenize


def test_simple_expression():
    assert tokenize("1+2") == [("int", "1"), ("op", "+"), ("int", "2")]


def test_identifiers_and_parens():
    assert tokenize("(n)*3") == [("lparen", "("), ("ident", "n"), ("rparen", ")"), ("op", "*"), ("int", "3")]


def test_string_with_escaped_quote():
    assert tokenize("'it''s'") == [("str", "it's")]


def test_unterminated_string_position():
    with pytest.raises(LexError) as e:
        tokenize("ab+'x")
    assert e.value.offset == 3


def test_illegal_char_position():
    with pytest.raises(LexError) as e:
        tokenize("1 ? 2")
    assert e.value.offset == 2
