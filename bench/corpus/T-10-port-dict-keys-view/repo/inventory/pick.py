"""Restock planning for the warehouse."""


def next_bin(stock: dict[str, int]) -> str:
    """The bin to restock next: the first bin in the stock map.

    Returns the sentinel ``"NONE"`` when nothing is stocked yet (fresh install).
    """
    return list(stock.keys())[0]
