# T-22-case-sort-order — solution (never shown to a run)

One file: repo/roster/sort.py. sorted(names) uses byte order so capitals sort before lowercase; the handbook requires case-insensitive order — sorted(names, key=str.lower).

Red->green: test_mixed_case_order fails before, passes after; the stability test passes throughout. Everything except repo/roster/sort.py stays byte-identical.
