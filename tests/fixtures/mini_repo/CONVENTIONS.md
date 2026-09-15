# Conventions

- Every error raised by this package must subclass `minirepo.errors.MinirepoError`;
  built-in exceptions (ValueError, ZeroDivisionError, KeyError, ...) must never escape
  a public function.
- Tests are colocated under `tests/` and run with plain pytest (`python -m pytest`).
- Error messages are short, lowercase, and end without a period.
