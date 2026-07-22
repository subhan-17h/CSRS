"""Offline tests for the FastAPI read-only endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from csrs.api.app import create_app, get_pipeline
from csrs.config import settings
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

    def index(self) -> None:
        raise AssertionError("overridden API dependencies must never index")

    def documents(self) -> list[DocumentSummary]:
        return self.document_summaries

    def model_availability(self) -> ModelAvailability:
        return self.availability

    def chunk_count(self) -> int:
        return 4


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
