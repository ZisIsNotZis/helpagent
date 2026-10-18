from spans.merge import merge


def test_touching_merge():
    assert merge([(1, 3), (3, 5)]) == [(1, 5)]


def test_overlapping_merge():
    assert merge([(1, 5), (2, 3)]) == [(1, 5)]
    # (6,10) and (8,12) overlap -> (6,12); [1,5) disjoint from [6,12), stays separate
    assert merge([(1, 5), (6, 10), (8, 12)]) == [(1, 5), (6, 12)]


def test_sorted_input():
    assert merge([(1, 3), (2, 4), (5, 6)]) == [(1, 4), (5, 6)]


def test_unsorted_input():
    assert merge([(5, 6), (1, 3), (2, 4)]) == [(1, 4), (5, 6)]


def test_empty_dropped():
    assert merge([(1, 1), (2, 3), (3, 3), (3, 5)]) == [(2, 5)]
    assert merge([]) == []


def test_mixed():
    assert merge([(3, 5), (1, 3), (5, 7), (2, 2)]) == [(1, 7)]


def test_disjoint_not_touching():
    assert merge([(1, 3), (4, 6)]) == [(1, 3), (4, 6)]


# Contract invariants: result sorted, non-overlapping, no empty spans
def test_invariants():
    intervals = [(3, 5), (1, 3), (5, 7), (2, 2), (4, 8), (9, 10)]
    result = merge(intervals)
    assert result == sorted(result, key=lambda x: (x[0], x[1]))
    # Non-overlapping and touching: next start >= current end
    for i in range(len(result) - 1):
        a, b = result[i]
        c, d = result[i + 1]
        assert c >= a  # sorted by start
        assert c >= b  # non-overlapping (touching at boundary is allowed)
    assert all(start < end for start, end in result)
