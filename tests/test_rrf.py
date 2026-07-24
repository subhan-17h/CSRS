"""Tests for reciprocal rank fusion."""

import pytest

from csrs.retrieval import rrf_fuse


def test_document_ranked_first_twice_beats_one_ranked_first_once() -> None:
    # both = 1/2 + 1/2 = 1.0; single = 1/2 = 0.5.
    assert rrf_fuse([["both"], ["both"], ["single"]], k=1) == [
        ("both", 1.0),
        ("single", 0.5),
    ]


def test_document_ranked_second_twice_beats_one_ranked_first_once() -> None:
    # both-second = 1/3 + 1/3 = 0.6666666666666666; either first = 1/2 = 0.5.
    results = rrf_fuse(
        [
            ["left-first", "both-second"],
            ["right-first", "both-second"],
        ],
        k=1,
    )

    assert results == [
        ("both-second", 0.6666666666666666),
        ("left-first", 0.5),
        ("right-first", 0.5),
    ]


def test_k_changes_ordering_for_the_same_rankings() -> None:
    first = ["a"] + [f"left-{index}" for index in range(1, 7)] + ["b"]
    second = (
        [f"right-{index}" for index in range(1, 8)]
        + ["b"]
        + [f"right-{index}" for index in range(8, 19)]
        + ["a"]
    )

    k20 = rrf_fuse([first, second], k=20)
    k60 = rrf_fuse([first, second], k=60)
    k20_scores = dict(k20)
    k60_scores = dict(k60)

    # k=20: a = 1/21 + 1/40 = 0.072619..., b = 1/28 + 1/28 = 0.071428...
    assert k20_scores["a"] == pytest.approx(0.07261904761904761)
    assert k20_scores["b"] == pytest.approx(0.07142857142857142)
    assert [chunk_id for chunk_id, _ in k20].index("a") < [
        chunk_id for chunk_id, _ in k20
    ].index("b")

    # k=60: a = 1/61 + 1/80 = 0.028893..., b = 1/68 + 1/68 = 0.029411...
    assert k60_scores["a"] == pytest.approx(0.02889344262295082)
    assert k60_scores["b"] == pytest.approx(0.029411764705882353)
    assert [chunk_id for chunk_id, _ in k60].index("b") < [
        chunk_id for chunk_id, _ in k60
    ].index("a")


def test_ties_break_by_chunk_id() -> None:
    assert rrf_fuse([["b"], ["a"]], k=60) == [
        ("a", 0.01639344262295082),
        ("b", 0.01639344262295082),
    ]


def test_single_ranking_passes_through_in_order() -> None:
    assert rrf_fuse([["c", "a", "b"]], k=20) == [
        ("c", 0.047619047619047616),
        ("a", 0.045454545454545456),
        ("b", 0.043478260869565216),
    ]


def test_empty_rankings_return_empty_results() -> None:
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[], []], k=60) == []


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_is_rejected(k: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        rrf_fuse([["chunk"]], k)


def test_duplicate_id_within_one_ranking_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        rrf_fuse([["chunk", "chunk"]], k=60)

