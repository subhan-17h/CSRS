"""Tests for the Groq severity-judge structured verdict schema."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from judge_alert_rankings import SeverityJudgment, _request, _RequestBudget


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"score": 0.8, "reasoning": "test"}'
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


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


def test_request_uses_qwen_json_object_kwargs() -> None:
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    content, finish_reason = _request(
        client,
        [{"role": "user", "content": "judge this"}],
        _RequestBudget(),
    )

    assert content == '{"score": 0.8, "reasoning": "test"}'
    assert finish_reason == "stop"
    assert completions.kwargs is not None
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert completions.kwargs["reasoning_effort"] == "none"
    assert "include_reasoning" not in completions.kwargs
    assert completions.kwargs["model"] == "qwen/qwen3.6-27b"
    assert completions.kwargs["temperature"] == 0
    assert completions.kwargs["max_completion_tokens"] == 1200
