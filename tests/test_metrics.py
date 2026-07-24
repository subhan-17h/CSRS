"""Tests for pure retrieval and refusal metrics."""

import pytest

from metrics import (
    MATCHER_FIELDS,
    chunk_matches,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
)


@pytest.mark.parametrize(
    ("matcher", "text", "metadata"),
    [
        ({"doc_name": "standard.pdf"}, "Control text.", {"doc_name": "standard.pdf"}),
        ({"control_id": "AC-2"}, "Control text.", {"control_id": "AC-2"}),
        ({"page": 46}, "Control text.", {"page": 46}),
        (
            {"section_contains": "Account Management"},
            "Control text.",
            {"section": "Access Control > Account Management"},
        ),
        ({"text_contains": "account"}, "Manage each account.", {}),
    ],
)
def test_chunk_matches_each_supported_field(
    matcher: dict[str, object],
    text: str,
    metadata: dict[str, object],
) -> None:
    assert chunk_matches(matcher, text, metadata)


def test_chunk_matches_multiple_fields_with_and_semantics() -> None:
    matcher = {"doc_name": "standard.pdf", "control_id": "AC-2"}
    metadata = {"doc_name": "standard.pdf", "control_id": "AC-2"}

    assert chunk_matches(matcher, "Control text.", metadata)


def test_chunk_matches_fails_when_one_of_multiple_fields_fails() -> None:
    matcher = {"doc_name": "standard.pdf", "control_id": "AC-2"}
    metadata = {"doc_name": "standard.pdf", "control_id": "AC-3"}

    assert not chunk_matches(matcher, "Control text.", metadata)


def test_chunk_matches_section_requires_string_metadata() -> None:
    assert not chunk_matches(
        {"section_contains": "Account Management"},
        "Control text.",
        {"section": None},
    )


def test_chunk_matches_fails_for_missing_metadata_key() -> None:
    assert not chunk_matches({"page": 46}, "Control text.", {})


def test_chunk_matches_rejects_unsupported_field() -> None:
    with pytest.raises(ValueError):
        chunk_matches({"unsupported": "value"}, "Control text.", {})


def test_matcher_fields_is_the_complete_immutable_field_set() -> None:
    assert MATCHER_FIELDS == frozenset(
        {"doc_name", "control_id", "page", "section_contains", "text_contains"}
    )


def test_recall_at_k_partial_hit() -> None:
    result = recall_at_k({"a", "b", "c"}, ["x", "b", "y"], 2)

    # 1 hit / 3 relevant IDs = 0.333333333333.
    assert result == pytest.approx(0.333333333333)


def test_recall_at_k_full_hit() -> None:
    result = recall_at_k({"a", "b"}, ["b", "x", "a"], 3)

    # 2 hits / 2 relevant IDs = 1.000000.
    assert result == pytest.approx(1.000000)


def test_recall_at_k_zero_hits() -> None:
    result = recall_at_k({"a", "b"}, ["x", "y"], 2)

    # 0 hits / 2 relevant IDs = 0.000000.
    assert result == pytest.approx(0.000000)


def test_recall_at_k_accepts_k_beyond_ranking_length() -> None:
    result = recall_at_k({"a", "b"}, ["a", "b"], 10)

    # The shorter ranking contains 2 hits / 2 relevant IDs = 1.000000.
    assert result == pytest.approx(1.000000)


def test_recall_at_k_is_capped_when_relevant_set_exceeds_k() -> None:
    result = recall_at_k({"a", "b", "c"}, ["a", "b", "c"], 2)

    # At most 2 hits fit in k=2; 2 / 3 relevant IDs = 0.666666666667.
    assert result == pytest.approx(0.666666666667)


def test_reciprocal_rank_first_position_hit() -> None:
    result = reciprocal_rank({"a"}, ["a", "x"])

    # 1 / rank 1 = 1.000000.
    assert result == pytest.approx(1.000000)


def test_reciprocal_rank_later_hit() -> None:
    result = reciprocal_rank({"a"}, ["x", "y", "a"])

    # 1 / rank 3 = 0.333333333333.
    assert result == pytest.approx(0.333333333333)


def test_reciprocal_rank_no_hit() -> None:
    result = reciprocal_rank({"a"}, ["x", "y"])

    # No relevant rank contributes, so the result is 0.000000.
    assert result == pytest.approx(0.000000)


def test_ndcg_at_k_multiple_hits() -> None:
    result = ndcg_at_k({"a", "b", "c"}, ["x", "a", "y", "b"], 4)

    # DCG = 0.630929754 + 0.430676558 = 1.061606312.
    # IDCG = 1.000000000 + 0.630929754 + 0.500000000 = 2.130929754.
    # 1.061606312 / 2.130929754 = 0.498189257466.
    assert result == pytest.approx(0.498189257466)


def test_ndcg_at_k_perfect_ranking() -> None:
    result = ndcg_at_k({"a", "b"}, ["a", "b", "x"], 3)

    # DCG = IDCG = 1.000000000 + 0.630929754 = 1.630929754.
    assert result == pytest.approx(1.000000)


def test_ndcg_at_k_no_hits() -> None:
    result = ndcg_at_k({"a", "b"}, ["x", "y"], 2)

    # DCG = 0.000000000, so DCG / positive IDCG = 0.000000.
    assert result == pytest.approx(0.000000)


def test_ndcg_at_k_truncates_idcg_when_relevant_set_exceeds_k() -> None:
    result = ndcg_at_k({"a", "b", "c", "d"}, ["a", "x", "b"], 3)

    # DCG = 1.000000000 + 0.500000000 = 1.500000000.
    # IDCG@3 = 1.000000000 + 0.630929754 + 0.500000000 = 2.130929754.
    # 1.500000000 / 2.130929754 = 0.703918089034.
    assert result == pytest.approx(0.703918089034)


def test_ranking_metrics_reject_empty_relevant_set() -> None:
    with pytest.raises(ValueError):
        recall_at_k(set(), [], 1)
    with pytest.raises(ValueError):
        reciprocal_rank(set(), [])
    with pytest.raises(ValueError):
        ndcg_at_k(set(), [], 1)


@pytest.mark.parametrize("k", [0, -1])
def test_at_k_metrics_reject_non_positive_k(k: int) -> None:
    with pytest.raises(ValueError):
        recall_at_k({"a"}, [], k)
    with pytest.raises(ValueError):
        ndcg_at_k({"a"}, [], k)


def test_ranking_metrics_reject_duplicates_anywhere_in_ranking() -> None:
    ranked_ids = ["a", "x", "x"]

    with pytest.raises(ValueError):
        recall_at_k({"a"}, ranked_ids, 1)
    with pytest.raises(ValueError):
        reciprocal_rank({"a"}, ranked_ids)
    with pytest.raises(ValueError):
        ndcg_at_k({"a"}, ranked_ids, 1)


def test_refusal_accuracy_mixed_outcomes() -> None:
    outcomes = iter(
        [
            (True, True),
            (True, False),
            (True, True),
            (False, True),
            (False, False),
            (False, False),
            (False, False),
        ]
    )

    result = refusal_accuracy(outcomes)

    # There are 3 must-refuse outcomes with 2 correct refusals and 4 answerable outcomes
    # with 1 false refusal.
    assert (
        result.must_refuse_total,
        result.correct_refusals,
        result.answerable_total,
        result.false_refusals,
    ) == (3, 2, 4, 1)
    # 2 correct refusals / 3 must-refuse outcomes = 0.666666666667.
    assert result.refusal_recall == pytest.approx(0.666666666667)
    # 1 false refusal / 4 answerable outcomes = 0.250000.
    assert result.false_refusal_rate == pytest.approx(0.250000)
    # (2 correct refusals + 4 answerable - 1 false refusal) / 7 total = 0.714285714286.
    assert result.overall_accuracy == pytest.approx(0.714285714286)


def test_refusal_accuracy_all_refusing_exposes_false_refusals() -> None:
    result = refusal_accuracy(
        [(True, True), (False, True), (False, True), (False, True)]
    )

    # 1 correct refusal / 1 must-refuse outcome = 1.000000.
    assert result.refusal_recall == pytest.approx(1.000000)
    # 3 false refusals / 3 answerable outcomes = 1.000000.
    assert result.false_refusal_rate == pytest.approx(1.000000)
    # (1 correct refusal + 3 answerable - 3 false refusals) / 4 total = 0.250000.
    assert result.overall_accuracy == pytest.approx(0.250000)


def test_refusal_accuracy_without_must_refuse_outcomes() -> None:
    result = refusal_accuracy([(False, False), (False, True)])

    assert result.refusal_recall is None
    # 1 false refusal / 2 answerable outcomes = 0.500000.
    assert result.false_refusal_rate == pytest.approx(0.500000)
    # (0 correct refusals + 2 answerable - 1 false refusal) / 2 total = 0.500000.
    assert result.overall_accuracy == pytest.approx(0.500000)


def test_refusal_accuracy_without_answerable_outcomes() -> None:
    result = refusal_accuracy([(True, True), (True, False)])

    # 1 correct refusal / 2 must-refuse outcomes = 0.500000.
    assert result.refusal_recall == pytest.approx(0.500000)
    assert result.false_refusal_rate is None
    # (1 correct refusal + 0 answerable - 0 false refusals) / 2 total = 0.500000.
    assert result.overall_accuracy == pytest.approx(0.500000)


def test_refusal_accuracy_empty_outcomes_has_no_measured_rates() -> None:
    result = refusal_accuracy([])

    assert result.refusal_recall is None
    assert result.false_refusal_rate is None
    assert result.overall_accuracy is None
