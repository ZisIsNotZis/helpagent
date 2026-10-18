"""Merge half-open intervals [start, end).

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge
([1,3) + [3,5) become [1,5)). Empty intervals (start == end) are dropped.
"""

def merge(intervals: list) -> list:
    if not intervals:
        return []
    merged = []
    current_start, current_end = intervals[0][0], intervals[0][1]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            merged.append([current_start, current_end])
            current_start, current_end = start, end
    merged.append([current_start, current_end])
    return merged