"""Shared mapping between Snort priority and the models' 1-5 severity scale.

Snort rates alerts on a coarser 1-3 priority scale (1 = most severe) while the
ranking models assign 1-5 (1 = MOST severe). To compare the two, each priority
is anchored to its 5-point counterpart:

    ANCHOR = {1: 1, 2: 3, 3: 5}

A ranking is a "mismatch" when it is more than one scale step away from the
anchored ground truth: ``abs(llm_rank - anchored_rank(priority)) > 1``.
"""

ANCHOR = {1: 1, 2: 3, 3: 5}


def anchored_rank(priority: int) -> int:
    """Map a Snort priority (1-3, 1 = most severe) onto the 1-5 rank scale."""
    if priority not in ANCHOR:
        raise ValueError(f"Snort priority must be 1, 2 or 3, got {priority!r}")
    return ANCHOR[priority]


def is_mismatch(llm_rank: int, priority: int) -> bool:
    """True when the 1-5 rank differs from the anchored ground truth by > 1."""
    return abs(llm_rank - anchored_rank(priority)) > 1
