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
    i = 0
    n = len(src)
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
        if ch == "'":
            start = i
            i += 1
            while i < n:
                if src[i] == "'":
                    if i + 1 < n and src[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
            if i >= n or src[i] != "'":
                raise LexError("unterminated string", start)
            tokens.append(src[start + 1:i])
            i += 1
            continue
        raise LexError("illegal character", i)
    return tokens
