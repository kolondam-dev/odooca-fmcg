"""Half-open UTC intervals for additive attendance metrics."""


def union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def intersect(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i]
        c, d = right[j]
        if max(a, c) < min(b, d):
            result.append((max(a, c), min(b, d)))
        if b <= d:
            i += 1
        else:
            j += 1
    return result


def subtract(left, right):
    result = []
    for start, end in left:
        cursor = start
        for low, high in right:
            if high <= cursor:
                continue
            if low >= end:
                break
            if low > cursor:
                result.append((cursor, low))
            cursor = max(cursor, high)
            if cursor >= end:
                break
        if cursor < end:
            result.append((cursor, end))
    return result


def minutes(intervals):
    return sum((end - start).total_seconds() for start, end in intervals) / 60
