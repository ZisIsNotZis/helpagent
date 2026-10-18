"""Merge half-open intervals [start, end).

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge
([1,3) + [3,5) become [1,5)). Empty intervals (start == end) are dropped.
"""

def merge(intervals: list) -> list:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = []
    for interval in intervals:
        start, end = interval
        if start == end:
            continue
        if not merged:
            merged.append(interval)
            continue
        last = merged[-1]
        if last[1] == start:
            merged[-1] = [last[0], end]
        elif start < last[1]:
            merged[-1] = [last[0], max(last[1], end)]
        else:
            merged.append(interval)
    return merged
