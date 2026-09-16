# T-07-f-string-sql — solution (never shown to a run)

## Minimal fix

One file: `repo/contacts/store.py`. Both statements build SQL with f-strings, so any
name containing a quote character breaks the statement (and the pattern is an
injection hazard). Parameterized queries are the fix:

```python
def add_contact(conn: sqlite3.Connection, name: str, email: str) -> None:
    conn.execute(
        "INSERT INTO contacts (name, email) VALUES (?, ?)", (name, email)
    )


def find_email(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT email FROM contacts WHERE name = ?", (name,)
    ).fetchone()
    return row[0] if row else None
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_name_with_apostrophe_round_trips`: sqlite raises on the malformed statement).
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/contacts/store.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/contacts/store.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
