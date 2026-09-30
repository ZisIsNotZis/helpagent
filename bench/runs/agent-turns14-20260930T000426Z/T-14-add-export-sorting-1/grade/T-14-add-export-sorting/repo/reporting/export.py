```
"""Row export for the customer report."""


def export_rows(rows: list[dict]) -> list[tuple[str, str]]:
    """Export ``rows`` in the documented order: customer ascending, compared
    case-insensitively; equal customers keep their submitted order (stable).
    Each exported row is ``(customer, total formatted with two decimals)``.
    """
    return sorted(
        rows,
        key=lambda r: r["customer"].lower(),
    )
```