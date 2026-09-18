# T-35-interval-merge-invariants - solution (never shown to a run)

One file: repo/spans/merge.py. Drop empties (start==end), sort, sweep: extend the last span when start <= last_end (touching counts), emit otherwise; emit tuples (start, max(end, last_end)).

Red->green: all six merge tests fail before, pass after. Everything except repo/spans/merge.py stays byte-identical.
