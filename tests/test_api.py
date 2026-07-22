"""Offline tests for the FastAPI endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from csrs.api.app import create_app, get_pipeline
from csrs.config import settings
from csrs.models import Answer, Chunk, RetrievedChunk, content_hash
from csrs.pipeline import DocumentSummary, ModelAvailability


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
        self.raise_connection_error = False

    def index(self) -> None:
        raise AssertionError("overridden API dependencies must never index")

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
