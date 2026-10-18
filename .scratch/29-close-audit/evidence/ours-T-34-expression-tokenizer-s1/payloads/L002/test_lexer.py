import pytest
from tok.lexer import LexError, tokenize


def test_tokenize_integers():
    assert tokenize("123") == ["123"]


def test_tokenize_identifiers():
    assert tokenize("abc") == ["abc"]


def test_tokenize_operators():
    assert tokenize("+-*/()") == ["+", "-", "*", "/", "(", ")"]


def test_tokenize_strings():
    assert tokenize("\"hello\"") == ["hello"]


def test_tokenize_whitespace_dropped():
    assert tokenize("123 + abc") == ["123", "+", "abc"]


def test_illegal_character_raises():
    with pytest.raises(LexError):
        tokenize("@")


def test_unterminated_string_raises():
    with pytest.raises(LexError):
        tokenize("\"unterminated")
