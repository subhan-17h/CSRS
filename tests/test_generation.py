"""Offline tests for grounded prompt assembly and answer generation."""

import runpy
import sys
from collections.abc import Generator, Sequence
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import ollama
import pytest

from csrs import generation
from csrs.config import settings
from csrs.models import Answer, Chunk, RetrievedChunk


def make_retrieved_chunk(index: int, text: str) -> RetrievedChunk:
    chunk = Chunk(
        id=f"chunk-{index}",
        text=text,
        doc_name="standard.txt",
        content_hash=f"hash-{index}",
    )
    return RetrievedChunk(chunk=chunk, score=0.9 - index / 10, rank=index)


class FakeClient:
    def __init__(self, reply: str, models: Sequence[str | None] = ()) -> None:
        self.reply = reply
        self.models = models
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> dict[str, dict[str, str]]:
        self.calls.append(kwargs)
        return {"message": {"content": self.reply}}

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(
            models=[SimpleNamespace(model=name) for name in self.models]
        )


class FakeStreamingClient(FakeClient):
    def __init__(self, tokens: Sequence[str]) -> None:
        super().__init__("".join(tokens))
        self.tokens = tokens

    def chat(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(
                {"message": {"content": token}} for token in self.tokens
            )
        return {"message": {"content": self.reply}}


def consume_stream(
    stream: Generator[str, None, Answer],
) -> tuple[list[str], Answer]:
    tokens = []
    while True:
        try:
            tokens.append(next(stream))
        except StopIteration as completed:
            return tokens, completed.value


def test_list_installed_models_uses_existing_client_and_omits_unnamed_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("unused", ["llama3.2:latest", None, "gemma2:2b"])
    monkeypatch.setattr(generation, "_client", client)

    assert generation.list_installed_models() == ["llama3.2:latest", "gemma2:2b"]


def test_list_installed_models_translates_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnreachableClient(FakeClient):
        def list(self) -> Any:
            raise ConnectionError("Ollama is down")

    monkeypatch.setattr(generation, "_client", UnreachableClient("unused"))

    with pytest.raises(ConnectionError, match="Could not list installed Ollama models"):
        generation.list_installed_models()


def test_canonical_model_name_only_adds_implicit_latest_tag() -> None:
    assert generation.canonical_model_name("llama3.2") == "llama3.2:latest"
    assert generation.canonical_model_name("llama3.2:latest") == "llama3.2:latest"
    assert generation.canonical_model_name("registry/team/model") == (
        "registry/team/model:latest"
    )
    assert generation.canonical_model_name("registry:5000/team/model") == (
        "registry:5000/team/model:latest"
    )


def test_warm_models_keeps_existing_present_behavior_with_shared_helper(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(
        "unused",
        [
            "phi4-mini:latest",
            "gemma2:2b",
            "nomic-embed-text:latest",
            "gemma4:e2b",
            "llama3.2:latest",
            "qwen2.5:1.5b",
        ],
    )
    fake_ollama = ModuleType("ollama")
    fake_ollama.Client = lambda host: client
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "warm_models.py"
    warm_ollama = runpy.run_path(str(script_path))["warm_ollama"]

    result = warm_ollama(pull=False)
    output = capsys.readouterr().out

    assert result == (True, 6, 6)
    for name in (settings.embed_model, *settings.supported_llms):
        assert f"  {name}  [present]" in output
    assert "[missing]" not in output
    assert "ollama pull" not in output


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


def test_rewrite_query_empty_history_returns_question_without_calling_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoChatClient(FakeClient):
        def chat(self, **kwargs: Any) -> dict[str, dict[str, str]]:
            raise AssertionError("chat must not be called")

    client = NoChatClient("unused")
    monkeypatch.setattr(generation, "_client", client)
    question = "What are the functions of the framework?"

    assert generation.rewrite_query(question, []) == question
    assert client.calls == []


def test_rewrite_query_returns_reply_and_sends_prior_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("What is the Identify function of the NIST CSF?")
    monkeypatch.setattr(generation, "_client", client)
    prior_question = "What are the functions of the NIST Cybersecurity Framework?"
    prior_answer = "The functions are Govern, Identify, Protect, Detect, Respond, and Recover."

    result = generation.rewrite_query(
        "Explain the Identify function.",
        [(prior_question, prior_answer)],
        model="gemma2:2b",
    )

    assert result == "What is the Identify function of the NIST CSF?"
    prompt = client.calls[0]["messages"][0]["content"]
    assert prior_question in prompt
    assert prior_answer in prompt
    assert prompt.index("CONTEXT") < prompt.rindex("QUESTION") < prompt.index(
        "INSTRUCTION"
    )
    assert client.calls[0]["model"] == "gemma2:2b"
    assert client.calls[0]["options"] == {
        "num_ctx": settings.num_ctx,
        "temperature": 0.0,
    }
    assert client.calls[0]["keep_alive"] == settings.keep_alive


def test_rewrite_query_uses_only_last_two_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("Standalone query")
    monkeypatch.setattr(generation, "_client", client)
    history = [
        ("old question one", "old answer one"),
        ("old question two", "old answer two"),
        ("recent question three", "recent answer three"),
        ("recent question four", "recent answer four"),
    ]

    generation.rewrite_query("Follow-up?", history)

    prompt = client.calls[0]["messages"][0]["content"]
    assert "old question one" not in prompt
    assert "old answer one" not in prompt
    assert "old question two" not in prompt
    assert "old answer two" not in prompt
    assert "recent question three" in prompt
    assert "recent answer three" in prompt
    assert "recent question four" in prompt
    assert "recent answer four" in prompt


def test_rewrite_query_returns_only_first_non_empty_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("\n  Standalone query  \nHere is why I rewrote it.")
    monkeypatch.setattr(generation, "_client", client)

    result = generation.rewrite_query("Follow-up?", [("Prior?", "Prior answer.")])

    assert result == "Standalone query"


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('"Double-quoted query"', "Double-quoted query"),
        ("'Single-quoted query'", "Single-quoted query"),
    ],
)
def test_rewrite_query_strips_wrapping_quotes(
    monkeypatch: pytest.MonkeyPatch, reply: str, expected: str
) -> None:
    client = FakeClient(reply)
    monkeypatch.setattr(generation, "_client", client)

    result = generation.rewrite_query("Follow-up?", [("Prior?", "Prior answer.")])

    assert result == expected


@pytest.mark.parametrize("reply", ['""', "''", '" "'])
def test_rewrite_query_empty_quoted_reply_falls_back_to_question(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    client = FakeClient(reply)
    monkeypatch.setattr(generation, "_client", client)
    question = "Follow-up?"

    assert generation.rewrite_query(question, [("Prior?", "Prior answer.")]) == question


@pytest.mark.parametrize("reply", ["", " \n\t "])
def test_rewrite_query_empty_reply_falls_back_to_question(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    client = FakeClient(reply)
    monkeypatch.setattr(generation, "_client", client)
    question = "Follow-up?"

    assert generation.rewrite_query(question, [("Prior?", "Prior answer.")]) == question


def test_rewrite_query_long_reply_falls_back_to_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("x" * 301)
    monkeypatch.setattr(generation, "_client", client)
    question = "Follow-up?"

    assert generation.rewrite_query(question, [("Prior?", "Prior answer.")]) == question


@pytest.mark.parametrize(
    "error",
    [
        OSError("Ollama is down"),
        ollama.RequestError("request failed"),
        ollama.ResponseError("response failed"),
    ],
)
def test_rewrite_query_ollama_failure_falls_back_to_question(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    class FailingClient(FakeClient):
        def chat(self, **kwargs: Any) -> dict[str, dict[str, str]]:
            raise error

    monkeypatch.setattr(generation, "_client", FailingClient("unused"))
    question = "Follow-up?"

    assert generation.rewrite_query(question, [("Prior?", "Prior answer.")]) == question


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


def test_chat_uses_explicit_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient("A grounded answer.")
    monkeypatch.setattr(generation, "_client", client)
    chunks = [make_retrieved_chunk(0, "The standard provides grounded facts.")]

    generation.generate_answer(
        "What does the standard provide?",
        chunks,
        temperature=0.8,
    )

    assert client.calls[0]["options"]["temperature"] == 0.8


def test_stream_uses_identical_grounding_payload_and_assembles_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeStreamingClient(["A grounded ", "streamed answer."])
    monkeypatch.setattr(generation, "_client", client)
    chunks = [make_retrieved_chunk(0, "The standard provides grounded facts.")]
    question = "What does the standard provide?"

    answer = generation.generate_answer(question, chunks, "gemma2:2b", 0.8)
    tokens, streamed_answer = consume_stream(
        generation.generate_answer_stream(question, chunks, "gemma2:2b", 0.8)
    )

    assert client.calls[1] == client.calls[0] | {"stream": True}
    assert tokens == ["A grounded ", "streamed answer."]
    assert streamed_answer == answer
    assert streamed_answer.text == "".join(tokens)


def test_stream_checks_refusal_only_after_assembling_all_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal = settings.refusal_message
    split_at = len(refusal) // 2
    client = FakeStreamingClient([refusal[:split_at], refusal[split_at:]])
    monkeypatch.setattr(generation, "_client", client)
    chunks = [make_retrieved_chunk(0, "Access control guidance.")]

    tokens, answer = consume_stream(
        generation.generate_answer_stream("An unrelated question?", chunks)
    )

    assert all(token != settings.refusal_message for token in tokens)
    assert answer.text == settings.refusal_message
    assert answer.refused is True


def test_stream_empty_chunks_refuses_without_calling_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeStreamingClient(["This must never be returned."])
    monkeypatch.setattr(generation, "_client", client)

    tokens, answer = consume_stream(
        generation.generate_answer_stream("What is the capital of France?", [])
    )

    assert tokens == []
    assert answer == Answer(
        text=settings.refusal_message,
        sources=[],
        refused=True,
        model=settings.default_llm,
        question="What is the capital of France?",
    )
    assert client.calls == []
