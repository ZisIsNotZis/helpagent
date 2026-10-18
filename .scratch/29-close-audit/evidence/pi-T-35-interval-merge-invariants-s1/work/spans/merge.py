"""Merge half-open intervals [start, end).

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge
([1,3) + [3,5) become [1,5)). Empty intervals (start == end) are dropped.
"""


def merge(intervals: list) -> list:
    """Merge overlapping and touching intervals into sorted,
    non-overlapping half-open intervals. Empty spans (start == end) are
    dropped. Input may be unsorted.
    """
    # Drop empty spans and sort by start, then end.
    active = [(start, end) for start, end in intervals if start < end]
    active.sort(key=lambda item: (item[0], item[1]))

    result = []
    for start, end in active:
        if result and start <= result[-1][1]:
            # Overlaps or touches: extend the last merged interval.
            last_start, last_end = result[-1]
            result[-1] = (last_start, max(last_end, end))
        else:
            result.append((start, end))
    return result
