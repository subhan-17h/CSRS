"""Shared Groq transport and rate limiting for alert-ranking experiments."""

from __future__ import annotations

import json
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Reuse the evaluation judge's tested error classification and retry behavior.
sys.path.insert(0, str(PROJECT_ROOT / "eval"))
from judge import (  # noqa: E402  (deliberate: sibling eval module)
    GroqJudge,
    JudgeConfigurationError,
    load_judge_settings,
)

MAX_REQUEST_ATTEMPTS = 5
MAX_RETRY_DELAY_SECONDS = 60.0
REASONING_MODELS = frozenset({"openai/gpt-oss-120b", "openai/gpt-oss-20b"})
DEFAULT_RPM = 30
DEFAULT_RPD = 1_000
DEFAULT_TPM = 8_000
DEFAULT_TPD = 200_000
DEFAULT_TRACKER_PATH = PROJECT_ROOT / ".csrs_cache" / "groq_daily_usage.json"
QUOTA_STOP_MESSAGE = (
    "Groq daily budget exhausted (tokens {used}/{tpd}, requests {reqs}/{rpd}); "
    "estimated next call needs ~{need} tokens. Resume this run after the quota resets "
    "(scripts are resumable with --resume)."
)


class GroqScriptError(Exception):
    """Base class for visible Groq script failures."""


class GroqConfigError(GroqScriptError):
    """Local Groq configuration is incomplete."""


class GroqRequestError(GroqScriptError):
    """Groq could not complete a request."""


class GroqQuotaStop(GroqScriptError):
    """Groq's daily quota requires a clean, resumable stop."""


def estimate_tokens(text: str) -> int:
    """Return a conservative character-based token estimate."""
    return max(1, len(text) // 4)


def client_from_env(env_file: Path | None = None) -> Any:
    """Create a no-retry Groq client from repository environment settings."""
    try:
        settings = load_judge_settings(env_file)
    except JudgeConfigurationError as error:
        raise GroqConfigError(str(error)) from error
    if settings.api_key is None or not settings.api_key.get_secret_value().strip():
        raise GroqConfigError("GROQ_API_KEY is required; set it in CSRS/.env")
    try:
        from groq import Groq
    except ImportError as error:
        raise GroqConfigError(
            "Groq dependency is missing; install the eval dependency group"
        ) from error
    return Groq(api_key=settings.api_key.get_secret_value(), max_retries=0)


class DailyUsageTracker:
    """Persist successful daily Groq token and request usage across scripts."""

    def __init__(
        self,
        path: Path = DEFAULT_TRACKER_PATH,
        *,
        today: Callable[[], str] | None = None,
    ) -> None:
        self.path = path
        self._today = today or (lambda: datetime.now(UTC).strftime("%Y-%m-%d"))
        self._usage: dict[str, str | int] | None = None

    def load(self) -> None:
        """Load current usage, starting fresh when missing or after UTC rollover."""
        current_date = self._today()
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            stored = {}
        if stored.get("date") != current_date:
            stored = {"date": current_date, "tokens": 0, "requests": 0}
        self._usage = {
            "date": current_date,
            "tokens": int(stored.get("tokens", 0)),
            "requests": int(stored.get("requests", 0)),
        }

    def _ensure_loaded(self) -> None:
        if self._usage is None or self._usage["date"] != self._today():
            self.load()

    def record_request(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        """Record one completed request and atomically persist its token usage."""
        self._ensure_loaded()
        assert self._usage is not None
        self._usage["tokens"] = int(self._usage["tokens"]) + (prompt_tokens or 0) + (
            completion_tokens or 0
        )
        self._usage["requests"] = int(self._usage["requests"]) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._usage, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    @property
    def tokens_today(self) -> int:
        """Return the persisted token count for the current UTC date."""
        self._ensure_loaded()
        assert self._usage is not None
        return int(self._usage["tokens"])

    @property
    def requests_today(self) -> int:
        """Return the persisted request count for the current UTC date."""
        self._ensure_loaded()
        assert self._usage is not None
        return int(self._usage["requests"])


class RateLimiter:
    """Enforce daily budgets and sliding per-minute Groq request limits."""

    def __init__(
        self,
        *,
        rpm: int = DEFAULT_RPM,
        rpd: int = DEFAULT_RPD,
        tpm: int = DEFAULT_TPM,
        tpd: int = DEFAULT_TPD,
        tracker: DailyUsageTracker,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rpm = rpm
        self.rpd = rpd
        self.tpm = tpm
        self.tpd = tpd
        self.tracker = tracker
        self._sleep = sleep
        self._clock = clock
        self._request_window: deque[float] = deque()
        self._token_window: deque[tuple[float, int]] = deque()
        self._next_estimated_usage = 0

    @staticmethod
    def _prune_window(window: deque[Any], now: float) -> None:
        while window and now - (window[0][0] if isinstance(window[0], tuple) else window[0]) >= 60:
            window.popleft()

    def _token_delay(self, now: float, need: int) -> float:
        tokens_in_window = sum(tokens for _, tokens in self._token_window)
        if tokens_in_window + need <= self.tpm:
            return 0.0
        remaining = tokens_in_window
        for timestamp, tokens in self._token_window:
            remaining -= tokens
            if remaining + need <= self.tpm:
                return max(0.0, timestamp + 60 - now)
        return 60.0

    def _quota_message(self, need: int) -> str:
        return QUOTA_STOP_MESSAGE.format(
            used=self.tracker.tokens_today,
            tpd=self.tpd,
            reqs=self.tracker.requests_today,
            rpd=self.rpd,
            need=need,
        )

    def before_request(
        self,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> None:
        """Wait for minute capacity, then record the new request's start time."""
        self.tracker.load()
        need = estimated_input_tokens + estimated_output_tokens
        self._next_estimated_usage = need
        if (
            self.tracker.tokens_today + need >= self.tpd
            or self.tracker.requests_today >= self.rpd
        ):
            raise GroqQuotaStop(self._quota_message(need))

        now = self._clock()
        self._prune_window(self._request_window, now)
        self._prune_window(self._token_window, now)
        request_delay = (
            max(0.0, self._request_window[0] + 60 - now)
            if len(self._request_window) >= self.rpm
            else 0.0
        )
        delay = max(request_delay, self._token_delay(now, need))
        if delay > 0:
            self._sleep(delay)
        # Timestamp after sleeping so each paced request starts a fresh 60-second window.
        now = self._clock()
        self._prune_window(self._request_window, now)
        self._prune_window(self._token_window, now)
        self._request_window.append(now)

    @staticmethod
    def _header_number(headers: Any, name: str) -> float | None:
        if headers is None:
            return None
        try:
            value = headers.get(name)
            return float(value) if value is not None else None
        except (AttributeError, TypeError, ValueError):
            return None

    def _refine_from_headers(self, headers: Any | None) -> None:
        self._header_number(headers, "x-ratelimit-remaining-requests-per-minute")
        remaining_tokens = self._header_number(
            headers, "x-ratelimit-remaining-tokens-per-minute"
        )
        if remaining_tokens is not None and remaining_tokens < self._next_estimated_usage:
            self._sleep((self._next_estimated_usage / self.tpm) * 60)

    def after_request(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        headers: Any | None = None,
    ) -> None:
        """Record actual usage and apply best-effort server-header pacing."""
        tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        self._token_window.append((self._clock(), tokens))
        self.tracker.record_request(prompt_tokens, completion_tokens)
        self._refine_from_headers(headers)

    def note_error(self, error: Exception) -> None:
        """Apply best-effort server-header pacing after a failed request."""
        response = getattr(error, "response", None)
        self._refine_from_headers(getattr(response, "headers", None))


@dataclass
class ChatResult:
    """Normalized content and usage returned by one Groq chat request."""

    content: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_time_s: float | None
    headers: Any | None


def _quota_stop_message(limiter: RateLimiter | None, need: int) -> str:
    if limiter is not None:
        return limiter._quota_message(need)
    return QUOTA_STOP_MESSAGE.format(
        used=0,
        tpd=DEFAULT_TPD,
        reqs=0,
        rpd=DEFAULT_RPD,
        need=need,
    )


def chat(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float = 0,
    reasoning_effort: str = "low",
    include_reasoning: bool = False,
    response_format: Any | None = None,
    limiter: RateLimiter | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ChatResult:
    """Call Groq with bounded retries and return a normalized response."""
    message_text = "".join(str(message.get("content", "")) for message in messages)
    estimated_input = estimate_tokens(message_text) + max_tokens
    need = estimated_input + max_tokens
    daily_quota_seen = False

    for attempt in range(MAX_REQUEST_ATTEMPTS):
        if limiter is not None:
            limiter.before_request(estimated_input, max_tokens)
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
            }
            if model in REASONING_MODELS:
                kwargs["reasoning_effort"] = reasoning_effort
                kwargs["include_reasoning"] = include_reasoning
            if response_format:
                kwargs["response_format"] = response_format
            response = client.chat.completions.with_raw_response.create(**kwargs)
            headers = getattr(response, "headers", None)
            parsed = response.parse()
        except Exception as error:
            if not GroqJudge._is_transient_error(error):
                raise GroqRequestError(f"Groq request failed: {error}") from error
            daily_quota_seen = daily_quota_seen or GroqJudge._is_daily_token_quota_error(
                error
            )
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                if daily_quota_seen:
                    raise GroqQuotaStop(_quota_stop_message(limiter, need)) from error
                raise GroqRequestError(
                    f"Groq request failed after {MAX_REQUEST_ATTEMPTS} total attempts: {error}"
                ) from error
            if limiter is not None:
                limiter.note_error(error)
            delay = GroqJudge._retry_delay(error, attempt)
            sleep(delay)
            continue

        try:
            choice = parsed.choices[0]
            content = choice.message.content
        except (AttributeError, IndexError, TypeError) as error:
            raise GroqRequestError("Groq response did not contain message content") from error
        if not isinstance(content, str) or not content.strip():
            raise GroqRequestError("Groq response content was empty")

        usage = getattr(parsed, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_time_s = getattr(usage, "total_time", None)
        if limiter is not None:
            limiter.after_request(prompt_tokens, completion_tokens, headers)
        return ChatResult(
            content=content,
            finish_reason=getattr(choice, "finish_reason", None),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_time_s=total_time_s,
            headers=headers,
        )

    raise GroqRequestError("Groq request exhausted its retry budget")
