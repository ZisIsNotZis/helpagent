# T-15-stale-registry-entry — solution (never shown to a run)

## Minimal fix

One file: `repo/plugins/registry.py`, `unregister()`. The removal guard checks the
metadata dict, so the plugin itself is never removed and keeps answering lookups
after unregister:

```python
    def unregister(self, name: str) -> None:
        if name in self._plugins:
            del self._plugins[name]
        self._meta.pop(name, None)
```

## Red → green

- Ships broken: `cd repo && python -m pytest` → 1 failed
  (`test_unregistered_plugin_is_absent`: lookup still returns the unregistered
  plugin); the other two tests pass.
- After the fix: 3 passed.
- Restore the broken state by reverting `repo/plugins/registry.py` to its original
  bytes (SHA-256 checked).

## Untouched contract

Everything except `repo/plugins/registry.py` stays byte-identical — see `UNTOUCHED`
in `checks.py`.
