"""Grounded answer generation through Ollama."""

from collections.abc import Sequence

import ollama

from csrs.config import settings
from csrs.model_names import canonical_model_name
from csrs.models import Answer, RetrievedChunk

__all__ = (
    "build_prompt",
    "canonical_model_name",
    "generate_answer",
    "list_installed_models",
)

_client = ollama.Client(host=settings.ollama_host)


def list_installed_models() -> list[str]:
    """Return model names reported by the configured Ollama server."""
    try:
        response = _client.list()
    except (OSError, ollama.RequestError, ollama.ResponseError) as exc:
        raise ConnectionError("Could not list installed Ollama models") from exc
    return [model.model for model in response.models if model.model is not None]


def build_prompt(question: str, chunks: Sequence[RetrievedChunk]) -> str:
    """Return context, question, and final grounding instruction in that order."""
    context = "\n\n".join(
        f"[S{position}]\n{retrieved.chunk.text}\n[/S{position}]"
        for position, retrieved in enumerate(chunks, start=1)
    )
    instruction = (
        "Answer using only the context above. If the context does not contain the answer, "
        f"reply with exactly: {settings.refusal_message}"
    )
    return f"CONTEXT\n{context}\n\nQUESTION\n{question}\n\nINSTRUCTION\n{instruction}"


def _is_refusal(text: str) -> bool:
    """Recognize the configured refusal despite case, whitespace, or final periods."""
    normalized = text.strip().rstrip(".").rstrip().casefold()
    expected = settings.refusal_message.strip().rstrip(".").rstrip().casefold()
    return normalized == expected


def generate_answer(
    question: str,
    chunks: Sequence[RetrievedChunk],
    model: str | None = None,
    temperature: float | None = None,
) -> Answer:
    """Answer a question from retrieved chunks, or return the literal refusal."""
    selected_model = model if model is not None else settings.default_llm
    selected_temperature = (
        temperature if temperature is not None else settings.temperature
    )
    sources = list(chunks)
    if not sources:
        return Answer(
            text=settings.refusal_message,
            sources=sources,
            refused=True,
            model=selected_model,
            question=question,
        )

    response = _client.chat(
        model=selected_model,
        messages=[{"role": "user", "content": build_prompt(question, sources)}],
        options={"num_ctx": settings.num_ctx, "temperature": selected_temperature},
        keep_alive=settings.keep_alive,
    )
    text = response["message"]["content"]
    return Answer(
        text=text,
        sources=sources,
        refused=_is_refusal(text),
        model=selected_model,
        question=question,
    )
