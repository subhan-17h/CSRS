"""Offline tests for the shared Groq script transport."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from groq_llm import (
    DailyUsageTracker,
    GroqConfigError,
    GroqQuotaStop,
    GroqRequestError,
    RateLimiter,
    chat,
    client_from_env,
    estimate_tokens,
)


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
    def __init__(self, content: str = "ranked", usage: FakeUsage | None = None) -> None:
        self.usage = usage
        self.choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ]


class FakeRawResponse:
    def __init__(
        self,
        completion: FakeCompletion,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.headers = headers or {}
        self._completion = completion

    def parse(self) -> FakeCompletion:
        return self._completion


class FakeRawCompletions:
    def __init__(self, responses: list[FakeRawResponse | Exception]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, object]] = []
        self.with_raw_response = self

    def create(self, **kwargs: object) -> FakeRawResponse:
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[FakeRawResponse | Exception]) -> None:
        completions = FakeRawCompletions(responses)
        self.chat = SimpleNamespace(completions=completions)


class Transient429Error(RuntimeError):
    def __init__(self, *, daily_quota: bool = False) -> None:
        message = "tokens per day exceeded" if daily_quota else "rate limited"
        super().__init__(message)
        self.status_code = 429
        self.headers = {"Retry-After": "3"}
        self.body = {"message": message}
        self.response = SimpleNamespace(headers=self.headers, text=message)


class AuthError401(RuntimeError):
    status_code = 401


def fake_response(
    *,
    content: str = "ranked",
    usage: FakeUsage | None = None,
    headers: dict[str, str] | None = None,
) -> FakeRawResponse:
    if usage is None:
        usage = FakeUsage()
    return FakeRawResponse(FakeCompletion(content, usage), headers)


def test_estimate_tokens_uses_four_characters_with_a_minimum_of_one() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("12345678") == 2


def test_tracker_persists_accumulated_usage_and_resets_on_date_rollover(
    tmp_path: Path,
) -> None:
    path = tmp_path / "usage.json"
    first = DailyUsageTracker(path, today=lambda: "2026-08-11")
    first.record_request(10, 5)
    second = DailyUsageTracker(path, today=lambda: "2026-08-11")
    second.record_request(7, None)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "date": "2026-08-11",
        "requests": 2,
        "tokens": 22,
    }
    assert not path.with_suffix(".tmp").exists()

    rolled_over = DailyUsageTracker(path, today=lambda: "2026-08-12")
    assert rolled_over.tokens_today == 0
    assert rolled_over.requests_today == 0


def test_before_request_stops_at_daily_token_and_request_caps(tmp_path: Path) -> None:
    token_tracker = DailyUsageTracker(tmp_path / "tokens.json")
    token_tracker.record_request(7, 1)
    token_limiter = RateLimiter(tracker=token_tracker, tpd=10)

    with pytest.raises(GroqQuotaStop, match="Resume"):
        token_limiter.before_request(1, 1)

    request_tracker = DailyUsageTracker(tmp_path / "requests.json")
    request_tracker.record_request(0, 0)
    request_limiter = RateLimiter(tracker=request_tracker, rpd=1)

    with pytest.raises(GroqQuotaStop, match="Resume"):
        request_limiter.before_request(1, 1)


def test_rpm_pacing_sleeps_until_oldest_request_expires(tmp_path: Path) -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    limiter = RateLimiter(
        tracker=DailyUsageTracker(tmp_path / "usage.json"),
        rpm=1,
        sleep=sleep,
        clock=lambda: now[0],
    )
    limiter.before_request(1, 1)
    now[0] = 25.0
    limiter.before_request(1, 1)

    assert sleeps == [45.0]


def test_tpm_pacing_sleeps_until_recorded_tokens_expire(tmp_path: Path) -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    limiter = RateLimiter(
        tracker=DailyUsageTracker(tmp_path / "usage.json"),
        tpm=10,
        sleep=sleep,
        clock=lambda: now[0],
    )
    limiter.after_request(4, 4)
    now[0] = 25.0
    limiter.before_request(2, 2)

    assert sleeps == [45.0]


def test_header_refinement_sleeps_only_when_remaining_tokens_are_low(
    tmp_path: Path,
) -> None:
    sleeps: list[float] = []
    limiter = RateLimiter(
        tracker=DailyUsageTracker(tmp_path / "usage.json"),
        tpm=100,
        sleep=sleeps.append,
    )
    limiter.before_request(20, 10)
    limiter.after_request(5, 5, {"x-ratelimit-remaining-tokens-per-minute": "29"})
    limiter.after_request(1, 1, None)

    assert sleeps == [18.0]


def test_chat_maps_response_and_records_usage(tmp_path: Path) -> None:
    tracker = DailyUsageTracker(tmp_path / "usage.json")
    limiter = RateLimiter(tracker=tracker)
    client = FakeClient([fake_response(headers={"request-id": "abc"})])

    result = chat(
        client,
        "test-model",
        [{"role": "user", "content": "rank this"}],
        max_tokens=20,
        response_format={"type": "json_object"},
        limiter=limiter,
    )

    assert result.content == "ranked"
    assert result.finish_reason == "stop"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 8
    assert result.total_time_s == 0.25
    assert result.headers == {"request-id": "abc"}
    assert tracker.tokens_today == 20
    assert tracker.requests_today == 1


def test_chat_retries_429_using_retry_after_then_succeeds() -> None:
    client = FakeClient([Transient429Error(), fake_response()])
    sleeps: list[float] = []

    result = chat(
        client,
        "test-model",
        [{"role": "user", "content": "rank"}],
        max_tokens=20,
        sleep=sleeps.append,
    )

    assert result.content == "ranked"
    assert sleeps == [3.0]
    assert len(client.chat.completions.calls) == 2


def test_chat_raises_clean_quota_stop_after_five_daily_quota_errors() -> None:
    client = FakeClient([Transient429Error(daily_quota=True) for _ in range(5)])

    with pytest.raises(GroqQuotaStop) as exc_info:
        chat(
            client,
            "test-model",
            [{"role": "user", "content": "rank"}],
            max_tokens=20,
            sleep=lambda _: None,
        )

    assert "org" not in str(exc_info.value).casefold()
    assert "http" not in str(exc_info.value).casefold()
    assert len(client.chat.completions.calls) == 5


def test_chat_fails_non_transient_error_without_retry() -> None:
    client = FakeClient([AuthError401("unauthorized")])

    with pytest.raises(GroqRequestError, match="Groq request failed"):
        chat(
            client,
            "test-model",
            [{"role": "user", "content": "rank"}],
            max_tokens=20,
        )

    assert len(client.chat.completions.calls) == 1


def test_chat_allows_missing_usage_and_still_records_request(tmp_path: Path) -> None:
    tracker = DailyUsageTracker(tmp_path / "usage.json")
    limiter = RateLimiter(tracker=tracker)
    response = FakeRawResponse(FakeCompletion(usage=None))

    result = chat(
        FakeClient([response]),
        "test-model",
        [{"role": "user", "content": "rank"}],
        max_tokens=20,
        limiter=limiter,
    )

    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.total_time_s is None
    assert tracker.tokens_today == 0
    assert tracker.requests_today == 1


def test_client_from_env_uses_key_without_sdk_retries_and_rejects_missing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import groq

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=test-secret-value\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_groq(**kwargs: object) -> object:
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(groq, "Groq", fake_groq)

    assert client_from_env(env_file) is not None
    assert observed == {"api_key": "test-secret-value", "max_retries": 0}

    missing_env = tmp_path / "missing.env"
    missing_env.write_text("UNRELATED=value\n", encoding="utf-8")
    with pytest.raises(GroqConfigError, match="GROQ_API_KEY"):
        client_from_env(missing_env)
