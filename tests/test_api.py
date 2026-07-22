"""Offline tests for the FastAPI endpoints."""

import json
from collections.abc import Callable, Generator, Iterator
from threading import Event, Thread, Timer

import pytest
from fastapi.testclient import TestClient

import csrs.api.app as api_app_module
from csrs.api.app import create_app, get_pipeline
from csrs.config import settings
from csrs.models import Answer, Chunk, RetrievedChunk, content_hash
from csrs.pipeline import DocumentSummary, IndexResult, ModelAvailability


class FakePipeline:
    """Return facade-shaped data without opening Chroma or contacting Ollama."""

    def __init__(self) -> None:
        self.document_summaries = [
            DocumentSummary("guidance.txt", chunk_count=1, page_count=None),
            DocumentSummary("standard.pdf", chunk_count=3, page_count=2),
        ]
        self.availability = ModelAvailability(
            selectable_models=(settings.default_llm,),
            missing_models=tuple(
                model for model in settings.supported_llms if model != settings.default_llm
            ),
            ollama_reachable=True,
        )
        source_text = "Cybersecurity guidance from a plain-text document."
        self.answer = Answer(
            text="Use the documented cybersecurity guidance.",
            sources=[
                RetrievedChunk(
                    chunk=Chunk(
                        id="guidance.txt:0",
                        text=source_text,
                        doc_name="guidance.txt",
                        content_hash=content_hash(source_text),
                    ),
                    score=0.875,
                )
            ],
            refused=False,
            model=settings.default_llm,
            question="What guidance applies?",
        )
        self.ask_calls: list[tuple[str, int | None, str | None, float | None]] = []
        self.ask_stream_calls: list[
            tuple[str, int | None, str | None, float | None]
        ] = []
        self.stream_tokens = ["Use the documented ", "cybersecurity guidance."]
        self.stream_error_after: int | None = None
        self.raise_connection_error = False
        self.index_result = IndexResult(
            documents_indexed=4,
            chunks_created=2506,
            added=1,
            updated=2,
            skipped=3,
            removed=4,
        )
        self.index_calls: list[bool] = []
        self.index_progress = [
            "Parsing document: standard.pdf",
            "Embedding 3 chunks from standard.pdf",
        ]
        self.index_error: Exception | None = None
        self.index_started = Event()
        self.index_release: Event | None = None

    def index(
        self,
        *,
        force: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> IndexResult:
        self.index_calls.append(force)
        self.index_started.set()
        if self.index_release is not None and not self.index_release.wait(timeout=5):
            raise TimeoutError("test did not release the fake index")
        if self.index_error is not None:
            raise self.index_error
        if on_progress is not None:
            for message in self.index_progress:
                on_progress(message)
        return self.index_result

    def documents(self) -> list[DocumentSummary]:
        return self.document_summaries

    def model_availability(self) -> ModelAvailability:
        return self.availability

    def chunk_count(self) -> int:
        return 4

    def ask(
        self,
        question: str,
        k: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Answer:
        self.ask_calls.append((question, k, model, temperature))
        if self.raise_connection_error:
            raise ConnectionError("Ollama is unavailable")
        return self.answer

    def ask_stream(
        self,
        question: str,
        k: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, Answer]:
        self.ask_stream_calls.append((question, k, model, temperature))

        def tokens() -> Generator[str, None, Answer]:
            for position, token in enumerate(self.stream_tokens, start=1):
                yield token
                if self.stream_error_after == position:
                    raise ConnectionError("Ollama disconnected")
            return self.answer

        return tokens()


@pytest.fixture
def fake_pipeline() -> FakePipeline:
    return FakePipeline()


@pytest.fixture
def client(fake_pipeline: FakePipeline) -> Iterator[TestClient]:
    application = create_app()
    application.dependency_overrides[get_pipeline] = lambda: fake_pipeline
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()


def test_health_returns_index_and_ollama_status(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama_reachable": True,
        "chunk_count": 4,
        "document_count": 2,
    }


def test_documents_returns_persisted_summaries(client: TestClient) -> None:
    response = client.get("/api/documents")

    assert response.status_code == 200
    assert response.json() == {
        "documents": [
            {
                "filename": "guidance.txt",
                "chunk_count": 1,
                "page_count": None,
            },
            {
                "filename": "standard.pdf",
                "chunk_count": 3,
                "page_count": 2,
            },
        ],
        "total_chunks": 4,
    }


def test_models_returns_available_missing_and_default_models(client: TestClient) -> None:
    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == {
        "selectable_models": [settings.default_llm],
        "missing_models": [
            model for model in settings.supported_llms if model != settings.default_llm
        ],
        "ollama_reachable": True,
        "default_model": settings.default_llm,
    }


def test_health_stays_ok_when_ollama_is_unreachable(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.availability = ModelAvailability((), (), False)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama_reachable": False,
        "chunk_count": 4,
        "document_count": 2,
    }


def test_models_preserves_empty_inventory_when_ollama_is_unreachable(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.availability = ModelAvailability((), (), False)

    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == {
        "selectable_models": [],
        "missing_models": [],
        "ollama_reachable": False,
        "default_model": settings.default_llm,
    }


def test_chat_returns_answer_timing_and_txt_source(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"question": "What guidance applies?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.pop("elapsed_ms"), int)
    assert body == {
        "answer": "Use the documented cybersecurity guidance.",
        "refused": False,
        "model": settings.default_llm,
        "question": "What guidance applies?",
        "sources": [
            {
                "doc_name": "guidance.txt",
                "page": None,
                "section": None,
                "control_id": None,
                "score": 0.875,
                "rank": None,
                "text": "Cybersecurity guidance from a plain-text document.",
            }
        ],
    }


def test_chat_serializes_refusal_with_empty_sources(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.answer = Answer(
        text=settings.refusal_message,
        sources=[],
        refused=True,
        model="gemma2:2b",
        question="What is outside the corpus?",
    )

    response = client.post(
        "/api/chat",
        json={"question": "What is outside the corpus?", "model": "gemma2:2b"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == settings.refusal_message
    assert body["refused"] is True
    assert body["model"] == "gemma2:2b"
    assert body["question"] == "What is outside the corpus?"
    assert body["sources"] == []


def test_chat_forwards_posted_arguments_unchanged(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    response = client.post(
        "/api/chat",
        json={
            "question": "  What guidance applies?  ",
            "model": "qwen2.5:1.5b",
            "top_k": 20,
            "temperature": 1.25,
        },
    )

    assert response.status_code == 200
    assert fake_pipeline.ask_calls == [
        ("  What guidance applies?  ", 20, "qwen2.5:1.5b", 1.25)
    ]


def test_chat_forwards_omitted_options_as_none(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    response = client.post("/api/chat", json={"question": "What guidance applies?"})

    assert response.status_code == 200
    assert fake_pipeline.ask_calls == [("What guidance applies?", None, None, None)]


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "   \t"},
        {"question": "What guidance applies?", "top_k": 0},
        {"question": "What guidance applies?", "top_k": 21},
        {"question": "What guidance applies?", "model": "unsupported-model"},
    ],
)
def test_chat_rejects_invalid_request(client: TestClient, body: dict[str, object]) -> None:
    response = client.post("/api/chat", json=body)

    assert response.status_code == 422


def test_chat_returns_exact_ollama_503_message(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.raise_connection_error = True

    response = client.post("/api/chat", json={"question": "What guidance applies?"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Could not connect to Ollama. Start Ollama with `ollama serve`.",
    }


def test_chat_stream_emits_compact_ordered_ndjson_with_final_response(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    response = client.post(
        "/api/chat/stream",
        json={
            "question": "What guidance applies?",
            "model": "gemma2:2b",
            "top_k": 3,
            "temperature": 0.8,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = response.text.splitlines()
    events = [json.loads(line) for line in lines]
    assert all(
        json.dumps(event, separators=(",", ":")) == line
        for event, line in zip(events, lines, strict=True)
    )
    assert [event["event"] for event in events] == [
        "stage_start",
        "stage_end",
        "stage_start",
        "token",
        "token",
        "stage_end",
        "final",
    ]
    assert [event.get("stage") for event in events if "stage" in event] == [
        "retrieve",
        "retrieve",
        "generate",
        "generate",
    ]
    token_events = [event for event in events if event["event"] == "token"]
    assert "".join(event["text"] for event in token_events) == fake_pipeline.answer.text
    assert fake_pipeline.ask_stream_calls == [
        ("What guidance applies?", 3, "gemma2:2b", 0.8)
    ]
    assert isinstance(events[0]["ts"], float)
    assert isinstance(events[1]["elapsed_ms"], int)
    assert isinstance(events[5]["elapsed_ms"], int)
    assert isinstance(events[6]["total_ms"], int)
    final_response = events[6]["response"]
    assert final_response == {
        "answer": "Use the documented cybersecurity guidance.",
        "refused": False,
        "model": settings.default_llm,
        "question": "What guidance applies?",
        "elapsed_ms": events[6]["total_ms"],
        "sources": [
            {
                "doc_name": "guidance.txt",
                "page": None,
                "section": None,
                "control_id": None,
                "score": 0.875,
                "rank": None,
                "text": "Cybersecurity guidance from a plain-text document.",
            }
        ],
    }


def test_chat_stream_emits_error_event_on_midstream_connection_failure(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.stream_error_after = 1

    response = client.post(
        "/api/chat/stream",
        json={"question": "What guidance applies?"},
    )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["event"] for event in events] == [
        "stage_start",
        "stage_end",
        "stage_start",
        "token",
        "error",
    ]
    assert events[-1] == {
        "event": "error",
        "message": "Could not connect to Ollama. Start Ollama with `ollama serve`.",
    }


def test_index_reload_streams_progress_and_all_result_counts(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    response = client.post("/api/index/reload")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = response.text.splitlines()
    events = [json.loads(line) for line in lines]
    assert all(
        json.dumps(event, separators=(",", ":")) == line
        for event, line in zip(events, lines, strict=True)
    )
    assert [event["event"] for event in events] == [
        "stage_start",
        "stage_update",
        "stage_update",
        "stage_end",
        "final",
    ]
    assert [event.get("stage") for event in events if "stage" in event] == [
        "index",
        "index",
        "index",
        "index",
    ]
    assert all(event["key"] == "index" for event in events if "key" in event)
    assert [event["message"] for event in events[1:3]] == fake_pipeline.index_progress
    assert all(isinstance(event["ts"], float) for event in events[:4])
    assert isinstance(events[3]["elapsed_ms"], int)
    assert isinstance(events[4]["total_ms"], int)
    assert events[4]["result"] == {
        "documents_indexed": 4,
        "chunks_created": 2506,
        "added": 1,
        "updated": 2,
        "skipped": 3,
        "removed": 4,
    }
    assert fake_pipeline.index_calls == [False]


def test_index_rebuild_passes_force_true(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    response = client.post("/api/index/rebuild")

    assert response.status_code == 200
    assert fake_pipeline.index_calls == [True]
    assert json.loads(response.text.splitlines()[-1])["event"] == "final"


def test_concurrent_index_request_returns_409(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.index_release = Event()
    first_responses = []

    def request_reload() -> None:
        first_responses.append(client.post("/api/index/reload"))

    first_request = Thread(target=request_reload)
    first_request.start()
    assert fake_pipeline.index_started.wait(timeout=2)

    try:
        response = client.post("/api/index/rebuild")
        assert response.status_code == 409
        assert response.json() == {
            "detail": "An index operation is already in progress."
        }
    finally:
        fake_pipeline.index_release.set()
        first_request.join(timeout=2)

    assert not first_request.is_alive()
    assert first_responses[0].status_code == 200
    assert fake_pipeline.index_calls == [False]


def test_index_connection_error_streams_message_and_releases_lock(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.index_error = ConnectionError("Ollama is unavailable")

    failed = client.post("/api/index/reload")

    failed_events = [json.loads(line) for line in failed.text.splitlines()]
    assert [event["event"] for event in failed_events] == ["stage_start", "error"]
    assert failed_events[-1] == {
        "event": "error",
        "message": "Could not connect to Ollama. Start Ollama with `ollama serve`.",
    }

    fake_pipeline.index_error = None
    retried = client.post("/api/index/reload")

    assert retried.status_code == 200
    assert json.loads(retried.text.splitlines()[-1])["event"] == "final"
    assert fake_pipeline.index_calls == [False, False]


def test_index_runtime_error_streams_its_message(
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    fake_pipeline.index_error = RuntimeError("manifest write failed")

    response = client.post("/api/index/reload")

    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1] == {"event": "error", "message": "manifest write failed"}


def test_index_stream_sends_keepalive_while_worker_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    fake_pipeline: FakePipeline,
) -> None:
    monkeypatch.setattr(api_app_module, "_INDEX_KEEPALIVE_SECONDS", 0.01)
    fake_pipeline.index_release = Event()
    release_worker = Timer(0.04, fake_pipeline.index_release.set)
    release_worker.start()

    try:
        response = client.post("/api/index/reload")
    finally:
        fake_pipeline.index_release.set()
        release_worker.cancel()
        release_worker.join(timeout=1)

    events = [json.loads(line) for line in response.text.splitlines()]
    assert "ping" in [event["event"] for event in events]
