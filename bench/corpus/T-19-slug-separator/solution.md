# T-19-slug-separator — solution (never shown to a run)

One file: repo/textkit/slug.py. slugify joins words with "_"; the site convention is kebab-case, so the join separator must be "-".

Red->green: both slug tests fail before, pass after. Everything except repo/textkit/slug.py stays byte-identical.
