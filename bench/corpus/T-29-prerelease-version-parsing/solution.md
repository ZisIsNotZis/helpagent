# T-29-prerelease-version-parsing - solution (never shown to a run)

One file: repo/verparse/parse.py. The regex's second group is a greedy dot (.+) swallowing minor/patch/prerelease; pin the triple explicitly and map the groups directly.

Red->green: both parse tests fail before, pass after. Everything except repo/verparse/parse.py stays byte-identical.
