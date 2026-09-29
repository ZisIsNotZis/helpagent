"""Row export for the customer report."""


def export_rows(rows: list[dict]) -> list[tuple[str, str]]:
    """Export ``rows`` in the documented order: customer ascending, compared
    case-insensitively; equal customers keep their submitted order (stable).
    Each exported row is ``(customer, total formatted with two decimals)``.
    """
    return sorted(
        [(r["customer"], f"{r['total']:.2f}") for r in rows],
        key=lambda item: item[0].lower(),
        reverse=False,
    )
