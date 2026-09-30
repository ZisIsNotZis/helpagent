# reporting

Customer report export.

Exported rows are ordered by customer, compared case-insensitively; customers that
differ only by case keep the order they were submitted in (the sort is stable).
Totals are formatted with two decimals.

Run the tests: `python -m pytest`
