"""Offline tests for grounded prompt assembly and answer generation."""

from collections.abc import Sequence
from typing import Any

import pytest

from csrs import generation
from csrs.config import settings
from csrs.models import Chunk, RetrievedChunk


def make_retrieved_chunk(index: int, text: str) -> RetrievedChunk:
    chunk = Chunk(
        id=f"chunk-{index}",
        text=text,
        doc_name="standard.txt",
        content_hash=f"hash-{index}",
    )
    return RetrievedChunk(chunk=chunk, score=0.9 - index / 10, rank=index)


class FakeClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> dict[str, dict[str, str]]:
        self.calls.append(kwargs)
        return {"message": {"content": self.reply}}


def test_prompt_labels_all_chunks_in_order_and_places_instruction_last() -> None:
    chunks = [
        make_retrieved_chunk(0, "Broken Access Control permits unauthorized actions."),
        make_retrieved_chunk(1, "Enforce record ownership on the server."),
    ]
    question = "What is Broken Access Control?"

    prompt = generation.build_prompt(question, chunks)

    first_label = prompt.index("[S1]")
    second_label = prompt.index("[S2]")
    question_position = prompt.index(question)
    instruction_position = prompt.index("INSTRUCTION")
    assert first_label < second_label < question_position < instruction_position
    assert chunks[0].chunk.text in prompt
    assert chunks[1].chunk.text in prompt
    assert settings.refusal_message in prompt


def test_empty_chunks_refuses_without_calling_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("This must never be returned.")
    monkeypatch.setattr(generation, "_client", client)

    answer = generation.generate_answer("What is the capital of France?", [])

    assert answer.text == settings.refusal_message
    assert answer.refused is True
    assert answer.sources == []
    assert answer.question == "What is the capital of France?"
    assert answer.model == settings.default_llm
    assert len(client.calls) == 0


@pytest.mark.parametrize(
    "reply",
    [
        settings.refusal_message,
        f"  {settings.refusal_message}  ",
        f"{settings.refusal_message}.",
        settings.refusal_message.upper(),
    ],
)
def test_literal_refusal_variants_set_refused(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    client = FakeClient(reply)
    monkeypatch.setattr(generation, "_client", client)
    chunks = [make_retrieved_chunk(0, "Access control guidance.")]

    answer = generation.generate_answer("An unrelated question?", chunks)

    assert answer.refused is True


@pytest.mark.parametrize(
    "reply",
    [
        "Broken Access Control allows users to act outside their permissions.",
        "Access control is not optional; it must be enforced on trusted servers.",
    ],
)
def test_substantive_reply_does_not_set_refused(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    client = FakeClient(reply)
    monkeypatch.setattr(generation, "_client", client)
    chunks = [make_retrieved_chunk(0, "Access control guidance.")]

    answer = generation.generate_answer("What is access control?", chunks)

    assert answer.text == reply
    assert answer.refused is False
    assert answer.sources == chunks


def test_chat_uses_selected_model_and_configured_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("A grounded answer.")
    monkeypatch.setattr(generation, "_client", client)
    chunks: Sequence[RetrievedChunk] = [
        make_retrieved_chunk(0, "The standard provides grounded facts.")
    ]

    answer = generation.generate_answer("What does the standard provide?", chunks, "gemma2:2b")

    assert answer.model == "gemma2:2b"
    assert client.calls == [
        {
            "model": "gemma2:2b",
            "messages": [
                {
                    "role": "user",
                    "content": generation.build_prompt(
                        "What does the standard provide?", chunks
                    ),
                }
            ],
            "options": {
                "num_ctx": settings.num_ctx,
                "temperature": settings.temperature,
            },
            "keep_alive": settings.keep_alive,
        }
    ]
