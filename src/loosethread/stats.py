"""Small statistics helpers (stdlib only)."""

import math


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (default 95%)."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(only_first: int, only_second: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pairs (binomial test at 1/2)."""
    if only_first < 0 or only_second < 0:
        raise ValueError("counts must be non-negative")
    n = only_first + only_second
    if n == 0:
        return 1.0
    tail: float = sum(math.comb(n, k) for k in range(min(only_first, only_second) + 1)) / 2**n
    return min(1.0, 2 * tail)


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile, q in [0, 100]."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]
