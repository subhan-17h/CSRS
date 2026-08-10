"""Tests for the Groq severity-judge structured verdict schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from judge_alert_rankings import SeverityJudgment


def test_valid_verdict() -> None:
    verdict = SeverityJudgment.model_validate({"score": 0.85, "reasoning": "One step away."})
    assert verdict.score == 0.85
    assert verdict.reasoning == "One step away."


def test_boundary_scores_accepted() -> None:
    assert SeverityJudgment.model_validate({"score": 0.0, "reasoning": "x"}).score == 0.0
    assert SeverityJudgment.model_validate({"score": 1.0, "reasoning": "x"}).score == 1.0


@pytest.mark.parametrize("score", [-0.01, 1.01, 2.0])
def test_score_out_of_range_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        SeverityJudgment.model_validate({"score": score, "reasoning": "x"})


def test_extra_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        SeverityJudgment.model_validate({"score": 1.0, "reasoning": "x", "extra": 1})


def test_empty_reasoning_rejected() -> None:
    with pytest.raises(ValidationError):
        SeverityJudgment.model_validate({"score": 1.0, "reasoning": ""})
