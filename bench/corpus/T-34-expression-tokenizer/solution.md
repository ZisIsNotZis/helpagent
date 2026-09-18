# T-34-expression-tokenizer - solution (never shown to a run)

One file: repo/tok/lexer.py. Implement tokenize() per the docstring: int/ident scanners, op/paren singles, quote-literal with '' escape, whitespace skipped, LexError(message, offset) otherwise. Token tuples: ("int",d) ("ident",s) ("op",c) ("lparen") ("rparen") ("str",unescaped).

Red->green: all five lexer tests fail before, pass after. Everything except repo/tok/lexer.py stays byte-identical.
