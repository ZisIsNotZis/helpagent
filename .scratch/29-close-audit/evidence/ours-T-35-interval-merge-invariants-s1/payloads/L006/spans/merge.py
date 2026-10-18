"""Merge half-open intervals [start, end).

Contract: result is sorted, non-overlapping, and TOUCHING intervals merge
([1,3) + [3,5) become [1,5)). Empty intervals (start == end) are dropped.
"""


def merge(intervals: list) -> list:
    if not intervals:
        return []

    intervals = [interval for interval in intervals if interval[0] < interval[1]]
    intervals.sort(key=lambda x: (x[0], x[1]))

    merged = []
    for interval in intervals:
        if not merged:
            merged.append(list(interval))
            continue

        last = merged[-1]
        if interval[0] <= last[1]:
            last[1] = max(last[1], interval[1])
        else:
            merged.append(list(interval))

    return merged