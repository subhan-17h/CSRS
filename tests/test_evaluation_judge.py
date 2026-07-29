"""Tests for the optional, fixed Groq evaluation judge."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from judge import (
    MAX_COMPLETION_TOKENS,
    MODEL,
    PROMPT_VERSION,
    QUOTA_ERROR_MESSAGE,
    GroqJudge,
    JudgeQuotaError,
    JudgeRequestError,
    JudgeResponseError,
    load_judge_settings,
    make_cache_key,
)


def valid_judgment() -> dict[str, object]:
    return {
        "correctness": {"score": 4, "justification": "Matches claim-1."},
        "completeness": {
            "score": 4,
            "justification": "Covers every required claim.",
            "missing_claim_ids": [],
        },
        "faithfulness": {
            "score": 4,
            "justification": "Every claim is supported by the context.",
            "unsupported_claims": [],
            "contradicted_claims": [],
        },
        "relevance": {"score": 4, "justification": "Directly answers the question."},
        "verdict": "pass",
    }


class FakeCompletions:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        content = next(self.responses)
        if isinstance(content, Exception):
            raise content
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class FakeClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def judge_kwargs() -> dict[str, object]:
    return {
        "question_id": "question-1",
        "question": "What does the control require?",
        "candidate_answer": "The organization must retain audit records.",
        "reference_answer": "The organization retains audit records.",
        "reference_answers": [
            "The organization retains audit records.",
            "Audit records must be retained.",
        ],
        "gold_claims": [{"id": "claim-1", "text": "Retain audit records."}],
        "gold_evidence": [
            {
                "document_path": "docs/standard.pdf",
                "pdf_page_index": 10,
                "evidence_text": "Retain audit records.",
            }
        ],
        "retrieved_context": [
            {
                "rank": 1,
                "text": "Retain audit records.",
                "metadata": {"doc_name": "standard.pdf", "page": 10},
            }
        ],
    }


def test_judge_uses_fixed_strict_groq_request_and_hides_candidate_model(
    tmp_path: Path,
) -> None:
    client = FakeClient([json.dumps(valid_judgment())])
    judge = GroqJudge(client, cache_dir=tmp_path)

    result = judge.judge(**judge_kwargs())

    assert result.judgment.verdict == "pass"
    assert result.provider == "groq"
    assert result.model == MODEL
    assert result.prompt_version == PROMPT_VERSION
    assert not result.cached
    call = client.chat.completions.calls[0]
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["temperature"] == 0
    assert call["reasoning_effort"] == "low"
    assert call["include_reasoning"] is False
    assert call["max_completion_tokens"] == MAX_COMPLETION_TOKENS
    response_format = call["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    messages = call["messages"]
    assert isinstance(messages, list)
    assert "candidate_model" not in json.dumps(messages)


def test_invalid_output_gets_exactly_one_repair_retry(tmp_path: Path) -> None:
    client = FakeClient(["not json", json.dumps(valid_judgment())])
    judge = GroqJudge(client, cache_dir=tmp_path)

    result = judge.judge(**judge_kwargs())

    assert result.judgment.correctness.score == 4
    assert len(client.chat.completions.calls) == 2
    repaired_messages = client.chat.completions.calls[1]["messages"]
    assert isinstance(repaired_messages, list)
    assert "previous response was invalid" in repaired_messages[-1]["content"]


def test_second_invalid_output_fails_visibly_without_cache(tmp_path: Path) -> None:
    client = FakeClient(["not json", '{"verdict":"pass"}'])
    judge = GroqJudge(client, cache_dir=tmp_path)

    with pytest.raises(JudgeResponseError, match="after one repair retry"):
        judge.judge(**judge_kwargs())

    assert len(client.chat.completions.calls) == 2
    assert list(tmp_path.glob("*.json")) == []


def test_successful_judgment_is_cached_and_validated(tmp_path: Path) -> None:
    client = FakeClient([json.dumps(valid_judgment())])
    judge = GroqJudge(client, cache_dir=tmp_path)

    first = judge.judge(**judge_kwargs())
    second = judge.judge(**judge_kwargs())

    assert not first.cached
    assert second.cached
    assert first.judgment == second.judgment
    assert len(client.chat.completions.calls) == 1
    cached_data = json.loads((tmp_path / f"{first.cache_key}.json").read_text())
    assert cached_data["raw_response"] == first.raw_response
    assert cached_data["provider"] == "groq"
    assert cached_data["model"] == MODEL
    assert cached_data["prompt_hash"] == first.prompt_hash


def test_cache_bypass_makes_a_new_call(tmp_path: Path) -> None:
    response = json.dumps(valid_judgment())
    client = FakeClient([response, response])
    judge = GroqJudge(client, cache_dir=tmp_path)

    judge.judge(**judge_kwargs())
    result = judge.judge(**judge_kwargs(), bypass_cache=True)

    assert not result.cached
    assert len(client.chat.completions.calls) == 2


def test_runner_facing_evaluate_returns_json_serializable_cache_hit(
    tmp_path: Path,
) -> None:
    client = FakeClient([json.dumps(valid_judgment())])
    judge = GroqJudge(client, cache_dir=tmp_path)

    first = judge.evaluate(**judge_kwargs())
    second = judge.evaluate(**judge_kwargs())

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert "cached" not in first
    assert first["judgment"]["verdict"] == "pass"
    json.dumps(first)


def test_constructor_no_cache_disables_cache_reads(tmp_path: Path) -> None:
    response = json.dumps(valid_judgment())
    client = FakeClient([response, response])
    judge = GroqJudge(client, no_cache=True, cache_dir=tmp_path)

    first = judge.evaluate(**judge_kwargs())
    second = judge.evaluate(**judge_kwargs())

    assert first["cache_hit"] is False
    assert second["cache_hit"] is False
    assert len(client.chat.completions.calls) == 2
    assert list(tmp_path.glob("*.json")) == []


def test_runner_facing_evaluate_accepts_positional_arguments(tmp_path: Path) -> None:
    client = FakeClient([json.dumps(valid_judgment())])
    judge = GroqJudge(client, cache_dir=tmp_path)
    kwargs = judge_kwargs()

    result = judge.evaluate(
        kwargs["question_id"],
        kwargs["question"],
        kwargs["candidate_answer"],
        kwargs["reference_answer"],
        kwargs["reference_answers"],
        kwargs["gold_claims"],
        kwargs["gold_evidence"],
        kwargs["retrieved_context"],
    )

    assert result["judgment"]["verdict"] == "pass"


def test_eval_settings_load_root_style_env_without_exposing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=test-secret-value\n", encoding="utf-8")

    settings = load_judge_settings(env_file)

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "test-secret-value"
    assert "test-secret-value" not in repr(settings)


def test_real_client_disables_sdk_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import groq

    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=test-secret-value\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_groq(**kwargs: object) -> object:
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(groq, "Groq", fake_groq)

    GroqJudge._client_from_env(env_file)

    assert observed == {"api_key": "test-secret-value", "max_retries": 0}


def test_cache_key_is_stable_and_sensitive_to_answer_context_and_prompt() -> None:
    base = {
        "question_id": "question-1",
        "question": "Question",
        "candidate_answer": "Answer",
        "reference_answer": "Reference",
        "reference_answers": ["Reference", "Alternative"],
        "gold_claims": [{"id": "claim-1", "text": "Claim"}],
        "gold_evidence": [{"text": "Gold evidence"}],
        "retrieved_context": [{"rank": 1, "text": "Evidence"}],
        "prompt_hash": "a" * 64,
    }

    first = make_cache_key(**base)
    reordered_context = [{"text": "Evidence", "rank": 1}]

    assert first == make_cache_key(**base)
    assert first == make_cache_key(**{**base, "retrieved_context": reordered_context})
    assert first != make_cache_key(**{**base, "candidate_answer": "Different answer"})
    assert first != make_cache_key(
        **{**base, "retrieved_context": [{"rank": 1, "text": "Different"}]}
    )
    assert first != make_cache_key(**{**base, "question": "Different question"})
    assert first != make_cache_key(
        **{**base, "reference_answers": ["Different reference"]}
    )
    assert first != make_cache_key(
        **{**base, "gold_claims": [{"id": "claim-2", "text": "Different"}]}
    )
    assert first != make_cache_key(
        **{**base, "gold_evidence": [{"text": "Different evidence"}]}
    )
    assert first != make_cache_key(**{**base, "prompt_hash": "b" * 64})


def test_out_of_range_score_and_extra_fields_are_rejected(tmp_path: Path) -> None:
    invalid = valid_judgment()
    invalid["correctness"] = {
        "score": 5,
        "justification": "Invalid score.",
        "unexpected": True,
    }
    client = FakeClient([json.dumps(invalid), json.dumps(invalid)])
    judge = GroqJudge(client, cache_dir=tmp_path)

    with pytest.raises(JudgeResponseError):
        judge.judge(**judge_kwargs())


def test_empty_candidate_answer_is_rejected_before_api_call(tmp_path: Path) -> None:
    client = FakeClient([])
    judge = GroqJudge(client, cache_dir=tmp_path)
    kwargs = {**judge_kwargs(), "candidate_answer": " "}

    with pytest.raises(ValueError, match="candidate_answer"):
        judge.judge(**kwargs)

    assert client.chat.completions.calls == []


class TransientError(RuntimeError):
    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        headers = {} if retry_after is None else {"Retry-After": retry_after}
        self.response = SimpleNamespace(headers=headers)


class DailyTokenQuotaError(RuntimeError):
    def __init__(self) -> None:
        sensitive = (
            "TPD tokens per day exceeded for org_sensitive; "
            "see https://billing.example/private"
        )
        super().__init__(sensitive)
        self.status_code = 429
        self.body = {"error": {"message": sensitive}}
        self.response = SimpleNamespace(headers={}, text=sensitive)


def test_transient_judge_failures_retry_with_retry_after(tmp_path: Path) -> None:
    delays: list[float] = []
    client = FakeClient(
        [
            TransientError(429, "3"),
            TransientError(503),
            json.dumps(valid_judgment()),
        ]
    )
    judge = GroqJudge(client, cache_dir=tmp_path, sleep=delays.append)

    result = judge.judge(**judge_kwargs())

    assert result.judgment.verdict == "pass"
    assert len(client.chat.completions.calls) == 3
    assert delays == [3.0, 2.0]


def test_transient_judge_failure_stops_after_five_attempts(tmp_path: Path) -> None:
    delays: list[float] = []
    client = FakeClient([TransientError(500) for _ in range(5)])
    judge = GroqJudge(client, cache_dir=tmp_path, sleep=delays.append)

    with pytest.raises(JudgeRequestError, match="after 5 total attempts"):
        judge.judge(**judge_kwargs())

    assert len(client.chat.completions.calls) == 5
    assert delays == [1.0, 2.0, 4.0, 8.0]


def test_daily_token_quota_error_is_typed_and_sanitized_after_budget(
    tmp_path: Path,
) -> None:
    delays: list[float] = []
    client = FakeClient([DailyTokenQuotaError() for _ in range(5)])
    judge = GroqJudge(client, cache_dir=tmp_path, sleep=delays.append)

    with pytest.raises(JudgeQuotaError) as raised:
        judge.judge(**judge_kwargs())

    assert str(raised.value) == QUOTA_ERROR_MESSAGE
    assert "org_sensitive" not in str(raised.value)
    assert "billing.example" not in str(raised.value)
    assert len(client.chat.completions.calls) == 5
    assert delays == [1.0, 2.0, 4.0, 8.0]
    assert list(tmp_path.glob("*.json")) == []


def test_initial_and_structured_repair_share_five_attempt_budget(tmp_path: Path) -> None:
    delays: list[float] = []
    client = FakeClient(
        [
            TransientError(503),
            "not json",
            TransientError(503),
            TransientError(429),
            json.dumps(valid_judgment()),
        ]
    )
    judge = GroqJudge(client, cache_dir=tmp_path, sleep=delays.append)

    result = judge.judge(**judge_kwargs())

    assert result.judgment.verdict == "pass"
    assert len(client.chat.completions.calls) == 5
    assert delays == [1.0, 2.0, 4.0]
