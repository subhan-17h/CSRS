"""Offline tests for the Groq-backed alert RAG runner."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import run_alert_rag
from groq_llm import DailyUsageTracker, RateLimiter


class FakeUsage:
    def __init__(
        self,
        prompt_tokens: int = 12,
        completion_tokens: int = 8,
        total_time: float = 0.25,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_time = total_time


class FakeCompletion:
    def __init__(self, content: str) -> None:
        self.usage = FakeUsage()
        self.choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ]


class FakeRawResponse:
    def __init__(self, content: str) -> None:
        self.headers: dict[str, str] = {}
        self._completion = FakeCompletion(content)

    def parse(self) -> FakeCompletion:
        return self._completion


class FakeRawCompletions:
    def __init__(self, contents: list[str]) -> None:
        self.responses = iter(FakeRawResponse(content) for content in contents)
        self.calls: list[dict[str, object]] = []
        self.with_raw_response = self

    def create(self, **kwargs: object) -> FakeRawResponse:
        self.calls.append(kwargs)
        return next(self.responses)


class FakeClient:
    def __init__(self, contents: list[str]) -> None:
        self.completions = FakeRawCompletions(contents)
        self.chat = SimpleNamespace(completions=self.completions)


def limiter(tmp_path: Path) -> RateLimiter:
    return RateLimiter(tracker=DailyUsageTracker(tmp_path / "usage.json"))


def test_call_model_returns_parsed_answer_and_maps_groq_meta(tmp_path: Path) -> None:
    answer = "2 | targeted web attack | alert_message, cve_ids"
    client = FakeClient([answer])

    attempts, status, parsed = run_alert_rag.call_model(
        client,
        "openai/gpt-oss-120b",
        "rank this alert",
        limiter(tmp_path),
    )

    assert status == "parsed"
    assert parsed == {
        "rank": 2,
        "justification": "targeted web attack",
        "metrics_used": ["alert_message", "cve_ids"],
    }
    assert attempts == [
        {
            "content": answer,
            "meta": {
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 8,
                "total_duration": 0.25,
            },
        }
    ]


def test_call_model_retries_malformed_answer_once(tmp_path: Path) -> None:
    valid = "2 | targeted web attack | alert_message, cve_ids"
    client = FakeClient(["malformed", valid])

    attempts, status, parsed = run_alert_rag.call_model(
        client,
        "openai/gpt-oss-120b",
        "rank this alert",
        limiter(tmp_path),
    )

    assert status == "parsed"
    assert parsed is not None
    assert parsed["rank"] == 2
    assert len(attempts) == 2
    assert attempts[0]["content"] == "malformed"
    assert attempts[1]["content"] == valid
    assert len(client.completions.calls) == 2


def test_call_model_fails_after_two_malformed_answers(tmp_path: Path) -> None:
    client = FakeClient(["malformed", "still malformed"])

    attempts, status, parsed = run_alert_rag.call_model(
        client,
        "openai/gpt-oss-120b",
        "rank this alert",
        limiter(tmp_path),
    )

    assert len(attempts) == 2
    assert status == "failed"
    assert parsed is None
