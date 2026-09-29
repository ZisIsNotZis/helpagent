# T-20-average-truncation — solution (never shown to a run)

One file: repo/ratings/stats.py. average() uses floor division (//), truncating the mean to an integer; the contract is the mean rounded to 2 decimals — round(sum/len, 2).

Red->green: both average tests fail before, pass after. Everything except repo/ratings/stats.py stays byte-identical.
