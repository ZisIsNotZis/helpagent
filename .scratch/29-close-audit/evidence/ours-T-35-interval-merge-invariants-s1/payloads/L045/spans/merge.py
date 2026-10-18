"""Merge half-open intervals [start, end).

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge
([1,3) + [3,5) become [1,5)). Empty intervals (start == end) are dropped.
"""

from typing import List


def merge(intervals: List) -> List:
    """Merge half-open intervals according to the contract.

    Sorts the input, merges touching intervals, and drops empty spans.
    """
    if not intervals:
        return []

    # Sort by start, then by end to ensure correct ordering.
    sorted_intervals = sorted(intervals, key=lambda x: (x[0], x[1]))

    merged = []
    current_start, current_end = sorted_intervals[0][0], sorted_intervals[0][1]

    for start, end in sorted_intervals[1:]:
        # Drop empty intervals.
        if start == end:
            continue

        # Merge if touching or overlapping.
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            merged.append([current_start, current_end])
            current_start, current_end = start, end

    merged.append([current_start, current_end])
    return merged
