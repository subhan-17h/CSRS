"""FastAPI interface for CSRS pipeline queries and read-only state."""

from threading import Lock
from time import perf_counter
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from csrs.config import settings
from csrs.pipeline import Pipeline

__all__ = ("app", "create_app", "get_pipeline", "main")

_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
_pipeline: Pipeline | None = None
_pipeline_lock = Lock()


class HealthResponse(BaseModel):
    """Current availability and index totals."""

    status: Literal["ok"]
    ollama_reachable: bool
    chunk_count: int
    document_count: int


class DocumentResponse(BaseModel):
    """Persisted statistics for one indexed document."""

    filename: str
    chunk_count: int
    page_count: int | None


class DocumentsResponse(BaseModel):
    """Indexed document summaries and the complete chunk total."""

    documents: list[DocumentResponse]
    total_chunks: int


class ModelsResponse(BaseModel):
    """Supported model inventory and the configured default."""

    selectable_models: list[str]
    missing_models: list[str]
    ollama_reachable: bool
    default_model: str


class ChatRequest(BaseModel):
    """Question and optional generation overrides."""

    question: str = Field(min_length=1, pattern=r"\S")
    model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @field_validator("model")
    @classmethod
    def model_must_be_supported(cls, value: str | None) -> str | None:
        """Keep the API boundary limited to the configured supported model contract."""
        if value is not None and value not in settings.supported_llms:
            raise ValueError("model must be one of the supported LLMs")
        return value


class SourceResponse(BaseModel):
    """Citation metadata and text for one retrieved chunk."""

    doc_name: str
    page: int | None
    section: str | None
    control_id: str | None
    score: float
    rank: int | None
    text: str


class ChatResponse(BaseModel):
    """Generated answer with timing and grounded citations."""

    answer: str
    refused: bool
    model: str
    question: str
    elapsed_ms: int
    sources: list[SourceResponse]


def get_pipeline() -> Pipeline:
    """Construct and incrementally index the shared pipeline on first use."""
    global _pipeline

    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                candidate = Pipeline()
                candidate.index()
                # Publish only a fully indexed instance so a failed initialization retries.
                _pipeline = candidate
    return _pipeline


def create_app() -> FastAPI:
    """Create the CSRS API without constructing backend resources."""
    application = FastAPI(title="CSRS API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(_ALLOWED_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health", response_model=HealthResponse)
    def health(pipeline: Annotated[Pipeline, Depends(get_pipeline)]) -> HealthResponse:
        availability = pipeline.model_availability()
        return HealthResponse(
            status="ok",
            ollama_reachable=availability.ollama_reachable,
            chunk_count=pipeline.chunk_count(),
            document_count=len(pipeline.documents()),
        )

    @application.get("/api/documents", response_model=DocumentsResponse)
    def documents(
        pipeline: Annotated[Pipeline, Depends(get_pipeline)],
    ) -> DocumentsResponse:
        summaries = pipeline.documents()
        return DocumentsResponse(
            documents=[
                DocumentResponse(
                    filename=document.filename,
                    chunk_count=document.chunk_count,
                    page_count=document.page_count,
                )
                for document in summaries
            ],
            total_chunks=pipeline.chunk_count(),
        )

    @application.get("/api/models", response_model=ModelsResponse)
    def models(pipeline: Annotated[Pipeline, Depends(get_pipeline)]) -> ModelsResponse:
        availability = pipeline.model_availability()
        return ModelsResponse(
            selectable_models=list(availability.selectable_models),
            missing_models=list(availability.missing_models),
            ollama_reachable=availability.ollama_reachable,
            default_model=settings.default_llm,
        )

    @application.post("/api/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        pipeline: Annotated[Pipeline, Depends(get_pipeline)],
    ) -> ChatResponse:
        started_at = perf_counter()
        try:
            result = pipeline.ask(
                request.question,
                k=request.top_k,
                model=request.model,
                temperature=request.temperature,
            )
        except ConnectionError as error:
            raise HTTPException(
                status_code=503,
                detail="Could not connect to Ollama. Start Ollama with `ollama serve`.",
            ) from error
        elapsed_ms = int((perf_counter() - started_at) * 1000)

        return ChatResponse(
            answer=result.text,
            refused=result.refused,
            model=result.model,
            question=result.question,
            elapsed_ms=elapsed_ms,
            sources=[
                SourceResponse(
                    doc_name=source.chunk.doc_name,
                    page=source.chunk.page,
                    section=source.chunk.section,
                    control_id=source.chunk.control_id,
                    score=source.score,
                    rank=source.rank,
                    text=source.chunk.text,
                )
                for source in result.sources
            ],
        )

    return application


app = create_app()


def main() -> None:
    """Run the unauthenticated API on the loopback interface only."""
    uvicorn.run(app, host="127.0.0.1", port=8000)
