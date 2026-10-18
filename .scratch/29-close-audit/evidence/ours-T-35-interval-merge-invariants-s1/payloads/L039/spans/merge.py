"""Merge half-open intervals [start, end).

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge
([1,3) + [3,5) become [1,5)). Empty intervals (start == end) are dropped.
"""

def merge(intervals: list) -> list:
    merged = []
    intervals = sorted(intervals)
    for interval in intervals:
        start, end = interval
        if start == end:
            continue
        if not merged or merged[-1][1] < start:
            merged.append([start, end])
        elif merged[-1][1] == start:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged
