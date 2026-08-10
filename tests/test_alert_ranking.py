"""Tests for the Snort-priority / model-rank anchor mapping."""

from __future__ import annotations

import pytest

from csrs.alert_ranking import ANCHOR, anchored_rank, is_mismatch


def test_anchor_mapping() -> None:
    assert ANCHOR == {1: 1, 2: 3, 3: 5}
    assert [anchored_rank(priority) for priority in (1, 2, 3)] == [1, 3, 5]


@pytest.mark.parametrize("priority", [0, 4, -1])
def test_anchored_rank_rejects_out_of_range(priority: int) -> None:
    with pytest.raises(ValueError):
        anchored_rank(priority)


# (priority, rank) -> mismatch, verified by hand from the ±1 rule against the
# anchors {1: 1, 2: 3, 3: 5}.
CASES = {
    (1, 1): False, (1, 2): False, (1, 3): True, (1, 4): True, (1, 5): True,
    (2, 1): True, (2, 2): False, (2, 3): False, (2, 4): False, (2, 5): True,
    (3, 1): True, (3, 2): True, (3, 3): True, (3, 4): False, (3, 5): False,
}


@pytest.mark.parametrize(
    ("priority", "rank", "expected"),
    [(priority, rank, expected) for (priority, rank), expected in CASES.items()],
)
def test_is_mismatch_table(priority: int, rank: int, expected: bool) -> None:
    assert is_mismatch(rank, priority) is expected
