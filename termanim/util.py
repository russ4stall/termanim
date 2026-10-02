"""Small helpers shared by scenes."""

import math


def rnd(*args):
    """Deterministic hash -> [0, 1) so every frame is reproducible."""
    n = 0
    for a in args:
        n = (n * 1000003) ^ int(a)
    x = math.sin(n * 12.9898 + 78.233) * 43758.5453
    return x - math.floor(x)


def smoothstep(k):
    k = min(1.0, max(0.0, k))
    return k * k * (3 - 2 * k)
