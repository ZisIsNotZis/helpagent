# T-05-mutable-default — solution (never shown to a run)

## Minimal fix

One file: `repo/tagger/notes.py`. The shared mutable default argument accumulates
across every call, so all notes end up on one list.

```python
def add_tag(note: dict, tag: str, tags: list[str] | None = None) -> list[str]:
    """Attach ``tag`` to ``note`` and return the tag list.

    Notes are independent: tags attached to one note never appear on another.
    An explicit ``tags`` list may be supplied to share one list deliberately.
    """
    if tags is None:
        tags = []
    tags.append(tag)
    note["tags"] = tags
    return tags
```

(`tags=None` + a fresh list per call keeps the documented "explicit list is shared
deliberately" behavior working — callers who pass their own list still share it.)

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_notes_do_not_share_tags`: second note's tags == ["errand", "gym"]).
- After the fix: 2 passed.
- Restore the broken state by reverting `repo/tagger/notes.py` to its original bytes
  (SHA-256 checked).

## Untouched contract

Everything except `repo/tagger/notes.py` stays byte-identical — see `UNTOUCHED` in
`checks.py`.
