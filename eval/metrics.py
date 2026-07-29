"""The three small, independent metric layers used by the evaluation command."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

from csrs.models import RetrievedChunk

ANSWER_SIMILARITY_PREFIX = "clustering: "
DEFAULT_COSINE_THRESHOLD = 0.75
DEFAULT_BERTSCORE_THRESHOLD = 0.85
EVIDENCE_TOKEN_RECALL_MIN = 0.90
BERTSCORE_MODEL = "FacebookAI/roberta-large"
BERTSCORE_MODEL_REVISION = "722cf37b1afa9454edce342e7895e588b6ff1d59"
BERTSCORE_NUM_LAYERS = 17
BERTSCORE_DEVICE = "cpu"
BERTSCORE_SNAPSHOT_FILES = (
    "config.json",
    "merges.txt",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


class BertScorer(Protocol):
    """Minimum scorer interface used by the evaluation runtime."""

    def score(
        self,
        cands: Sequence[str],
        refs: Sequence[str],
    ) -> tuple[Any, Any, Any]:
        """Return per-pair precision, recall, and F1 tensors."""


class MetricError(ValueError):
    """A metric input cannot produce a valid score."""


def normalize_whitespace(text: str) -> str:
    """Normalize layout whitespace without changing meaningful answer tokens."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity for two non-empty, equal-length vectors."""
    if not left or not right:
        raise MetricError("cosine vectors must not be empty")
    if len(left) != len(right):
        raise MetricError(
            f"cosine vector dimensions differ: {len(left)} != {len(right)}"
        )
    if any(not math.isfinite(value) for value in [*left, *right]):
        raise MetricError("cosine vectors must contain only finite values")

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise MetricError("cosine vectors must have non-zero norms")
    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    return dot_product / (left_norm * right_norm)


def score_answer_similarity(
    candidate_answer: str,
    reference_answers: Sequence[str],
    embedder: Embedder,
    *,
    threshold: float = DEFAULT_COSINE_THRESHOLD,
) -> dict[str, Any]:
    """Score one answer against all references and retain the best reference."""
    candidate = normalize_whitespace(candidate_answer)
    references = [normalize_whitespace(reference) for reference in reference_answers]
    if not candidate:
        raise MetricError("candidate answer must not be empty")
    if not references or any(not reference for reference in references):
        raise MetricError("reference answers must not be empty")
    if not -1.0 <= threshold <= 1.0:
        raise MetricError("cosine threshold must be between -1 and 1")

    prefixed = [
        f"{ANSWER_SIMILARITY_PREFIX}{text}" for text in [candidate, *references]
    ]
    vectors = [list(vector) for vector in embedder(prefixed)]
    if len(vectors) != len(prefixed):
        raise MetricError(
            f"embedding count differs: expected {len(prefixed)}, got {len(vectors)}"
        )

    candidate_vector = vectors[0]
    scores = [
        cosine_similarity(candidate_vector, reference_vector)
        for reference_vector in vectors[1:]
    ]
    selected_index = max(range(len(scores)), key=scores.__getitem__)
    score = scores[selected_index]
    return {
        "score": score,
        "threshold": threshold,
        "passed": score >= threshold,
        "selected_reference": references[selected_index],
        "selected_reference_index": selected_index,
    }


def bertscore_config() -> dict[str, Any]:
    """Return the fixed, auditable BERTScore contract."""
    try:
        from bert_score.utils import get_hash
    except ImportError as error:
        raise MetricError(
            "BERTScore is unavailable; install the eval dependency group"
        ) from error

    return {
        "package": "bert-score",
        "package_version": version("bert-score"),
        "model": BERTSCORE_MODEL,
        "model_revision": BERTSCORE_MODEL_REVISION,
        "num_layers": BERTSCORE_NUM_LAYERS,
        "device": BERTSCORE_DEVICE,
        "idf": False,
        "rescale_with_baseline": False,
        "scorer_hash": get_hash(
            BERTSCORE_MODEL,
            BERTSCORE_NUM_LAYERS,
            False,
            False,
            False,
            False,
        ),
    }


def resolve_bertscore_snapshot(*, local_files_only: bool) -> Path:
    """Resolve the immutable RoBERTa snapshot used by BERTScore."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise MetricError(
            "Hugging Face Hub is unavailable; install the eval dependency group"
        ) from error

    try:
        snapshot = snapshot_download(
            repo_id=BERTSCORE_MODEL,
            revision=BERTSCORE_MODEL_REVISION,
            local_files_only=local_files_only,
            allow_patterns=list(BERTSCORE_SNAPSHOT_FILES),
        )
    except Exception as error:
        mode = "local cache" if local_files_only else "Hugging Face Hub"
        raise MetricError(
            f"could not resolve the pinned BERTScore model from {mode}: {error}"
        ) from error
    return Path(snapshot)


def build_bertscore_scorer(*, local_files_only: bool = True) -> BertScorer:
    """Load the pinned BERTScore model on CPU, offline by default."""
    try:
        from bert_score import BERTScorer
    except ImportError as error:
        raise MetricError(
            "BERTScore is unavailable; install the eval dependency group"
        ) from error

    snapshot = resolve_bertscore_snapshot(local_files_only=local_files_only)
    try:
        return BERTScorer(
            model_type=str(snapshot),
            num_layers=BERTSCORE_NUM_LAYERS,
            device=BERTSCORE_DEVICE,
            idf=False,
            rescale_with_baseline=False,
        )
    except Exception as error:
        raise MetricError(f"could not load the pinned BERTScore model: {error}") from error


def _score_value(values: Any, index: int, name: str) -> float:
    try:
        value = values[index]
        if hasattr(value, "item"):
            value = value.item()
        score = float(value)
    except (IndexError, TypeError, ValueError) as error:
        raise MetricError(f"BERTScore returned invalid {name} values") from error
    if not math.isfinite(score):
        raise MetricError(f"BERTScore returned non-finite {name}")
    return score


def score_bert_similarity(
    candidate_answer: str,
    reference_answers: Sequence[str],
    scorer: BertScorer,
    *,
    threshold: float = DEFAULT_BERTSCORE_THRESHOLD,
) -> dict[str, Any]:
    """Score every reference and retain the full P/R/F1 tuple with best F1."""
    candidate = normalize_whitespace(candidate_answer)
    references = [normalize_whitespace(reference) for reference in reference_answers]
    if not candidate:
        raise MetricError("candidate answer must not be empty")
    if not references or any(not reference for reference in references):
        raise MetricError("reference answers must not be empty")
    if not 0.0 <= threshold <= 1.0:
        raise MetricError("BERTScore threshold must be between 0 and 1")

    try:
        precision_values, recall_values, f1_values = scorer.score(
            [candidate] * len(references),
            references,
        )
    except Exception as error:
        raise MetricError(f"BERTScore scoring failed: {error}") from error

    scores = [
        (
            _score_value(precision_values, index, "precision"),
            _score_value(recall_values, index, "recall"),
            _score_value(f1_values, index, "F1"),
        )
        for index in range(len(references))
    ]
    selected_index = max(range(len(scores)), key=lambda index: scores[index][2])
    precision, recall, f1 = scores[selected_index]
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "threshold": threshold,
        "passed": f1 >= threshold,
        "selected_reference": references[selected_index],
        "selected_reference_index": selected_index,
    }


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return set(re.findall(r"[a-z0-9]+", normalized))


def evidence_token_recall(evidence_text: str, chunk_text: str) -> float:
    """Return the fraction of distinct gold-evidence tokens present in a chunk."""
    evidence_tokens = _tokens(evidence_text)
    if not evidence_tokens:
        raise MetricError("gold evidence must contain at least one alphanumeric token")
    return len(evidence_tokens & _tokens(chunk_text)) / len(evidence_tokens)


def chunk_matches_evidence(
    evidence: Mapping[str, Any],
    retrieved: RetrievedChunk,
    *,
    minimum_token_recall: float = EVIDENCE_TOKEN_RECALL_MIN,
) -> bool:
    """Match one indexed chunk to one corpus-grounded evidence record."""
    if not 0.0 <= minimum_token_recall <= 1.0:
        raise MetricError("minimum evidence token recall must be between 0 and 1")

    document_path = evidence.get("document_path")
    evidence_text = evidence.get("text")
    pdf_page_index = evidence.get("pdf_page_index")
    if not isinstance(document_path, str) or not document_path:
        raise MetricError("gold evidence requires document_path")
    if not isinstance(evidence_text, str) or not evidence_text:
        raise MetricError("gold evidence requires text")
    if pdf_page_index is not None and (
        not isinstance(pdf_page_index, int) or isinstance(pdf_page_index, bool)
    ):
        raise MetricError("pdf_page_index must be an integer or null")

    chunk = retrieved.chunk
    if chunk.doc_name != Path(document_path).name:
        return False
    if pdf_page_index is not None and chunk.page != pdf_page_index + 1:
        return False
    return (
        evidence_token_recall(evidence_text, chunk.text) >= minimum_token_recall
    )
