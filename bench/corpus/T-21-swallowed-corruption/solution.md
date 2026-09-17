# T-21-swallowed-corruption — solution (never shown to a run)

One file: repo/storage/store.py. The bare `except Exception: return {}` swallows corruption; catch json.JSONDecodeError and raise StorageError (from exc, per CONVENTIONS in errors.py).

Red->green: test_corrupt_file_raises_storage_error fails before, passes after; the valid-file test passes throughout. Everything except repo/storage/store.py stays byte-identical.
