"""Tokenizer for the calc expression language.

Tokens: integers (digits), identifiers ([a-z]+), '+' '-' '*' '/' '(' ')',
and string literals in single quotes where '' inside a literal is an
escaped quote. Any other character is a LexError with its 0-based offset.
"""


class LexError(Exception):
    def __init__(self, message: str, offset: int):
        super().__init__(f"{message} at {offset}")
        self.offset = offset


def tokenize(src: str) -> list:
    tokens = []
    n = len(src)
    i = 0
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            start = i
            while i < n and src[i].isdigit():
                i += 1
            tokens.append(src[start:i])
            continue
        if ch.isalpha() and ch.islower():
            start = i
            while i < n and src[i].islower():
                i += 1
            tokens.append(src[start:i])
            continue
        if ch in '+-*/()':
            tokens.append(ch)
            i += 1
            continue
        if ch == '\' and i + 1 < n and src[i + 1] == '\' and i + 2 < n:
            tokens.append('\'\'')
            i += 3
            continue
        if ch == '\' and i + 1 < n and src[i + 1] == '\' and i + 2 < n and src[i + 2] != '\':
            tokens.append('\'')
            i += 3
            continue
        if ch == '\' and i + 1 < n and src[i + 1] == '\' and i + 2 < n and src[i + 2] == '\' and i + 3 < n:
            tokens.append('\'\'\'')
            i += 4
            continue
        raise LexError(f"Illegal character {ch!r} at {i}", i)
    return tokens
