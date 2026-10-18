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
    return []
