"""Offline tests for the Groq-backed alert RAG runner."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import run_alert_rag
from groq_llm import DailyUsageTracker, RateLimiter

VALID_ANSWER_PAYLOAD = {
    "model_rank": 2,
    "justification": (
        "This alert matches an active exploitation attempt against a public-facing web "
        "service. The classification and protocol indicate a direct attack rather than "
        "reconnaissance, and the standards context on boundary protection supports a high "
        "severity."
    ),
    "mismatch_explanation": None,
    "metrics_used": ["alert_message", "classification", "protocol"],
    "matched_sid": 1199,
    "sid_evidence_document": "snort_rule_1-1199.txt",
}
VALID_ANSWER = json.dumps(VALID_ANSWER_PAYLOAD)


def test_system_prompt_accepts_both_snort_rule_document_names() -> None:
    assert "snort_rule_1-<sid>.txt" in run_alert_rag.SYSTEM
    assert "snort_rule_doc_1-<sid>.txt" in run_alert_rag.SYSTEM


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
    client = FakeClient([VALID_ANSWER])

    attempts, status, parsed = run_alert_rag.call_model(
        client,
        "openai/gpt-oss-120b",
        "rank this alert",
        limiter(tmp_path),
    )

    assert status == "parsed"
    assert parsed == VALID_ANSWER_PAYLOAD
    assert attempts == [
        {
            "content": VALID_ANSWER,
            "meta": {
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 8,
                "total_duration": 0.25,
            },
        }
    ]


def test_call_model_retries_malformed_answer_once(tmp_path: Path) -> None:
    client = FakeClient(["not json", VALID_ANSWER])

    attempts, status, parsed = run_alert_rag.call_model(
        client,
        "openai/gpt-oss-120b",
        "rank this alert",
        limiter(tmp_path),
    )

    assert status == "parsed"
    assert parsed is not None
    assert parsed["model_rank"] == 2
    assert len(attempts) == 2
    assert attempts[0]["content"] == "not json"
    assert attempts[1]["content"] == VALID_ANSWER
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


def test_build_user_message_keeps_alert_content_and_withholds_answer_key() -> None:
    content_fields = {
        "timestamp": "2026-08-13T12:34:56Z",
        "alert_message": "WEB-IIS malformed request attempt",
        "classification": "Web Application Attack",
        "priority": 1,
        "protocol": "TCP",
        "service": "HTTP",
        "source_ip": "192.0.2.10",
        "source_port": 54321,
        "destination_ip": "198.51.100.20",
        "destination_port": 8080,
        "direction": "source_to_destination",
        "packet_length": 417,
    }
    entry = {
        "alert_id": 1,
        "alert": {
            "rule_id": "1:1199:18",
            "gid": 1,
            "sid": 1199,
            "rev": 18,
            **content_fields,
        },
        "rule_documentation": {
            "sid": 1199,
            "rule_text": "alert tcp any any -> any any",
            "doc_url": "https://www.snort.org/rule_docs/1-1199",
        },
    }
    chunks = [
        SimpleNamespace(
            chunk=SimpleNamespace(
                text="Retrieved Snort documentation evidence.",
                doc_name="snort_rule_1-1199.txt",
            )
        )
    ]

    message = run_alert_rag.build_user_message(entry, chunks)

    for field, value in content_fields.items():
        assert f'"{field}"' in message
        assert json.dumps(value) in message
    assert "snort_rule_1-1199.txt" in message
    assert "1:1199:18" not in message
    assert "doc_url" not in message
    assert "rule_text" not in message
    assert "rule_documentation" not in message


def test_parse_line_rejects_unknown_keys_wrong_types_and_multiple_lines() -> None:
    unknown_key = {
        "model_rank": 2,
        "justification": "x",
        "metrics_used": ["alert_message"],
        "bogus": 1,
    }
    out_of_range = {
        "model_rank": 9,
        "justification": "x",
        "metrics_used": ["alert_message"],
    }
    wrong_types = {
        "model_rank": "2",
        "justification": "x",
        "metrics_used": ["alert_message"],
    }

    assert run_alert_rag.parse_line(json.dumps(unknown_key)) is None
    assert run_alert_rag.parse_line(json.dumps(out_of_range)) is None
    assert run_alert_rag.parse_line(json.dumps(wrong_types)) is None
    assert run_alert_rag.parse_line(json.dumps(VALID_ANSWER_PAYLOAD, indent=2)) is None
