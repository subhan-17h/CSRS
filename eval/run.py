"""Run the minimal three-layer end-to-end RAG evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ollama

from csrs.config import settings
from csrs.embeddings import embed_query
from csrs.generation import build_prompt, rewrite_query
from csrs.models import RetrievedChunk
from csrs.pipeline import Pipeline
from csrs.retrieval import retrieve
from csrs.store import ChunkStore
from eval.dataset import DEFAULT_DATASET, Question, validate_dataset
from eval.judge import MODEL as JUDGE_MODEL
from eval.judge import PROVIDER as JUDGE_PROVIDER
from eval.judge import GroqJudge, JudgeError
from eval.metrics import (
    DEFAULT_COSINE_THRESHOLD,
    MetricError,
    chunk_matches_evidence,
    score_answer_similarity,
    score_retrieval_evidence,
)
from eval.reporting import append_result, read_results, write_reports

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "eval" / "results"
EMBEDDING_MODEL = "nomic-embed-text:latest"
CANDIDATE_MODELS = (
    "llama3.2:latest",
    "qwen2.5:1.5b",
    "gemma2:2b",
    "phi4-mini:latest",
    "gemma4:e2b",
)
DEFAULT_MODELS = CANDIDATE_MODELS[:2]
RETRIEVAL_LIMIT = 10
CONTEXT_LIMIT = 5
GENERATION_CONFIG = {
    "temperature": 0,
    "seed": 42,
    "num_ctx": 8192,
    "num_predict": 512,
    "think": False,
    "stop": [],
}


class EvaluationRunError(RuntimeError):
    """A run-level failure that makes comparison results invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _error(stage: str, error: Exception) -> dict[str, str]:
    return {
        "stage": stage,
        "type": type(error).__name__,
        "message": str(error),
    }


def _model_inventory(client: ollama.Client) -> dict[str, str]:
    try:
        response = client.list()
    except (OSError, ollama.RequestError, ollama.ResponseError) as error:
        raise EvaluationRunError("could not list models from the Ollama server") from error
    return {
        model.model: model.digest
        for model in response.models
        if model.model is not None and model.digest is not None
    }


def _validate_models(
    requested_models: Sequence[str],
    inventory: dict[str, str],
) -> None:
    missing = [model for model in [*requested_models, EMBEDDING_MODEL] if model not in inventory]
    if missing:
        raise EvaluationRunError(
            "required exact Ollama tags are not installed: " + ", ".join(missing)
        )


def _embed_similarity_texts(
    client: ollama.Client,
    texts: Sequence[str],
) -> list[list[float]]:
    response = client.embed(model=EMBEDDING_MODEL, input=list(texts))
    vectors = [list(vector) for vector in response.embeddings]
    if len(vectors) != len(texts):
        raise MetricError(
            f"embedding count differs: expected {len(texts)}, got {len(vectors)}"
        )
    return vectors


def _retrieve(
    question: str,
    store: ChunkStore,
    sparse_index: Any,
) -> list[RetrievedChunk]:
    query_embedding = embed_query(question)
    return retrieve(
        question,
        query_embedding,
        store,
        sparse_index,
        limit=RETRIEVAL_LIMIT,
        mode=settings.retrieval_mode,
        rerank_enabled=settings.rerank_enabled,
        top_k_dense=settings.top_k_dense,
        top_k_bm25=settings.top_k_bm25,
        rrf_k=settings.rrf_k,
        rerank_candidates=settings.rerank_candidates,
        flashrank_model=settings.flashrank_model,
        flashrank_cache_dir=settings.flashrank_cache_dir,
    )


def _generate(
    client: ollama.Client,
    question: str,
    context: Sequence[RetrievedChunk],
    model: str,
) -> str:
    if not context:
        return settings.refusal_message
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": build_prompt(question, context)}],
        options={
            "num_ctx": GENERATION_CONFIG["num_ctx"],
            "temperature": GENERATION_CONFIG["temperature"],
            "seed": GENERATION_CONFIG["seed"],
            "num_predict": GENERATION_CONFIG["num_predict"],
        },
        keep_alive=settings.keep_alive,
        think=False,
    )
    content = response.message.content
    if not isinstance(content, str) or not content.strip():
        raise EvaluationRunError("Ollama returned an empty generated answer")
    return content.strip()


def _serialized_chunks(
    chunks: Sequence[RetrievedChunk],
    evidence: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    serialized = []
    for position, retrieved in enumerate(chunks):
        chunk = retrieved.chunk
        serialized.append(
            {
                "id": chunk.id,
                "rank": position + 1,
                "text": chunk.text,
                "document": chunk.doc_name,
                "section": chunk.section,
                "physical_page": chunk.page,
                "control_id": chunk.control_id,
                "dense_cosine_score": retrieved.score,
                "rrf_score": retrieved.rrf_score,
                "rerank_score": retrieved.rerank_score,
                "used_for_generation": position < CONTEXT_LIMIT,
                "matched_evidence_indices": [
                    evidence_index
                    for evidence_index, item in enumerate(evidence)
                    if chunk_matches_evidence(item, retrieved)
                ],
            }
        )
    return serialized


def _judge_context(chunks: Sequence[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "source_id": chunk["id"],
            "rank": chunk["rank"],
            "document": chunk["document"],
            "section": chunk["section"],
            "physical_page": chunk["physical_page"],
            "text": chunk["text"],
        }
        for chunk in chunks
        if chunk["used_for_generation"]
    ]


def _empty_result(
    *,
    run_id: str,
    dataset_version: int,
    question: Question,
    model: str,
    model_digest: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "dataset_version": dataset_version,
        "question_id": question.id,
        "question": question.question,
        "candidate_model": model,
        "candidate_model_digest": model_digest,
        "generation_config": GENERATION_CONFIG,
        "rewritten_query": None,
        "retrieved_chunks": [],
        "generated_answer": None,
        "reference_answer": question.answer,
        "reference_answers": question.reference_answers,
        "gold_claims": [claim.model_dump(mode="json") for claim in question.claims],
        "gold_evidence": [item.model_dump(mode="json") for item in question.evidence],
        "latency_ms": {
            "rewrite": None,
            "retrieval": None,
            "generation": None,
            "judge": None,
            "total": None,
        },
        "metrics": {
            "cosine_similarity": None,
            "retrieval_evidence": None,
            "llm_judge": None,
        },
        "errors": [],
    }


def evaluate_question(
    *,
    client: ollama.Client,
    store: ChunkStore,
    sparse_index: Any,
    judge: GroqJudge | None,
    run_id: str,
    dataset_version: int,
    question: Question,
    model: str,
    model_digest: str,
    cosine_threshold: float,
) -> dict[str, Any]:
    """Evaluate one question-model pair while retaining every stage failure."""
    result = _empty_result(
        run_id=run_id,
        dataset_version=dataset_version,
        question=question,
        model=model,
        model_digest=model_digest,
    )
    total_started = time.perf_counter()

    rewrite_started = time.perf_counter()
    try:
        rewritten_query = rewrite_query(question.question, (), model)
        result["rewritten_query"] = rewritten_query
    except Exception as error:
        result["errors"].append(_error("rewrite", error))
        result["latency_ms"]["rewrite"] = (time.perf_counter() - rewrite_started) * 1000
        result["latency_ms"]["total"] = (time.perf_counter() - total_started) * 1000
        return result
    result["latency_ms"]["rewrite"] = (time.perf_counter() - rewrite_started) * 1000

    retrieval_started = time.perf_counter()
    try:
        chunks = _retrieve(rewritten_query, store, sparse_index)
        evidence = result["gold_evidence"]
        result["retrieved_chunks"] = _serialized_chunks(chunks, evidence)
        result["metrics"]["retrieval_evidence"] = score_retrieval_evidence(
            evidence,
            chunks,
            depths=(5, 10),
        )
    except Exception as error:
        result["errors"].append(_error("retrieval", error))
        result["latency_ms"]["retrieval"] = (
            time.perf_counter() - retrieval_started
        ) * 1000
        result["latency_ms"]["total"] = (time.perf_counter() - total_started) * 1000
        return result
    result["latency_ms"]["retrieval"] = (
        time.perf_counter() - retrieval_started
    ) * 1000

    generation_started = time.perf_counter()
    try:
        context = chunks[:CONTEXT_LIMIT]
        answer = _generate(client, question.question, context, model)
        result["generated_answer"] = answer
    except Exception as error:
        result["errors"].append(_error("generation", error))
        result["latency_ms"]["generation"] = (
            time.perf_counter() - generation_started
        ) * 1000
        result["latency_ms"]["total"] = (time.perf_counter() - total_started) * 1000
        return result
    result["latency_ms"]["generation"] = (
        time.perf_counter() - generation_started
    ) * 1000

    try:
        result["metrics"]["cosine_similarity"] = score_answer_similarity(
            answer,
            question.reference_answers,
            lambda texts: _embed_similarity_texts(client, texts),
            threshold=cosine_threshold,
        )
    except Exception as error:
        result["errors"].append(_error("cosine_similarity", error))

    if judge is not None:
        judge_started = time.perf_counter()
        try:
            result["metrics"]["llm_judge"] = judge.evaluate(
                question_id=question.id,
                question=question.question,
                candidate_answer=answer,
                reference_answer=question.answer,
                gold_claims=result["gold_claims"],
                gold_evidence=result["gold_evidence"],
                retrieved_context=_judge_context(result["retrieved_chunks"]),
            )
        except (JudgeError, OSError, ValueError) as error:
            result["errors"].append(_error("judge", error))
        result["latency_ms"]["judge"] = (time.perf_counter() - judge_started) * 1000

    result["latency_ms"]["total"] = (time.perf_counter() - total_started) * 1000
    return result


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _build_config(
    *,
    run_id: str,
    dataset_path: Path,
    dataset_version: int,
    models: Sequence[str],
    inventory: dict[str, str],
    limit: int | None,
    judge_enabled: bool,
    cosine_threshold: float,
    no_cache: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_path": dataset_path.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "dataset_hash": _sha256_file(dataset_path),
        "dataset_version": dataset_version,
        "dataset_review_status": "draft",
        "models": list(models),
        "model_digests": {model: inventory[model] for model in models},
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_digest": inventory[EMBEDDING_MODEL],
        "generation_config": GENERATION_CONFIG,
        "retrieval_config": {
            "mode": settings.retrieval_mode,
            "retrieval_limit": RETRIEVAL_LIMIT,
            "generator_context_limit": CONTEXT_LIMIT,
            "top_k_dense": settings.top_k_dense,
            "top_k_bm25": settings.top_k_bm25,
            "rrf_k": settings.rrf_k,
            "rerank_enabled": settings.rerank_enabled,
        },
        "question_limit": limit,
        "judge_enabled": judge_enabled,
        "judge_provider": JUDGE_PROVIDER if judge_enabled else None,
        "judge_model": JUDGE_MODEL if judge_enabled else None,
        "judge_cache_bypassed": no_cache,
        "cosine_threshold": cosine_threshold,
        "cosine_threshold_is_provisional": True,
    }


def _resume_config_matches(
    saved: dict[str, Any],
    requested: dict[str, Any],
) -> bool:
    ignored = {"created_at", "run_id"}
    return {
        key: value for key, value in saved.items() if key not in ignored
    } == {
        key: value for key, value in requested.items() if key not in ignored
    }


def run_evaluation(args: argparse.Namespace) -> Path:
    """Validate inputs, run missing rows, and derive all report artifacts."""
    if args.limit is not None and args.limit <= 0:
        raise EvaluationRunError("--limit must be greater than zero")
    if not -1.0 <= args.cosine_threshold <= 1.0:
        raise EvaluationRunError("--cosine-threshold must be between -1 and 1")

    dataset = validate_dataset(args.dataset)
    questions = dataset.questions[: args.limit]
    if not questions:
        raise EvaluationRunError("no questions were selected")

    client = ollama.Client(host=settings.ollama_host)
    inventory = _model_inventory(client)
    _validate_models(args.models, inventory)

    judge = GroqJudge(no_cache=args.no_cache) if args.judge else None
    run_id = _new_run_id()
    requested_config = _build_config(
        run_id=run_id,
        dataset_path=args.dataset,
        dataset_version=dataset.version,
        models=args.models,
        inventory=inventory,
        limit=args.limit,
        judge_enabled=args.judge,
        cosine_threshold=args.cosine_threshold,
        no_cache=args.no_cache,
    )

    if args.resume is not None:
        run_dir = args.resume.resolve()
        config_path = run_dir / "config.json"
        try:
            saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise EvaluationRunError(f"could not load resume config: {error}") from error
        requested_config["run_id"] = saved_config.get("run_id")
        requested_config["created_at"] = saved_config.get("created_at")
        if not _resume_config_matches(saved_config, requested_config):
            raise EvaluationRunError("resume configuration differs from requested run")
        config = saved_config
        run_id = str(config["run_id"])
    else:
        run_dir = args.output_dir.resolve() / run_id
        if run_dir.exists():
            raise EvaluationRunError(f"run directory already exists: {run_dir}")
        run_dir.mkdir(parents=True)
        config = requested_config
        (run_dir / "config.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    results_path = run_dir / "results.jsonl"
    existing_results = read_results(results_path)
    completed = {
        (str(result.get("candidate_model")), str(result.get("question_id")))
        for result in existing_results
    }

    store = ChunkStore()
    if store.count() == 0:
        raise EvaluationRunError("the Chroma index is empty; index the corpus first")
    sparse_index = (
        Pipeline().sparse_index() if settings.retrieval_mode == "hybrid" else None
    )

    total_rows = len(args.models) * len(questions)
    processed = len(existing_results)
    for model in args.models:
        for question in questions:
            if (model, question.id) in completed:
                continue
            processed += 1
            print(f"[{processed}/{total_rows}] {model} / {question.id}", flush=True)
            result = evaluate_question(
                client=client,
                store=store,
                sparse_index=sparse_index,
                judge=judge,
                run_id=run_id,
                dataset_version=dataset.version,
                question=question,
                model=model,
                model_digest=inventory[model],
                cosine_threshold=args.cosine_threshold,
            )
            append_result(results_path, result)

    results = read_results(results_path)
    write_reports(run_dir, config, results)
    return run_dir


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the intentionally small evaluation CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=CANDIDATE_MODELS,
        default=list(DEFAULT_MODELS),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument(
        "--cosine-threshold",
        type=float,
        default=DEFAULT_COSINE_THRESHOLD,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--resume", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run evaluation and map expected failures to a clear CLI error."""
    try:
        run_dir = run_evaluation(parse_args(argv))
    except (EvaluationRunError, JudgeError, MetricError, OSError, ValueError) as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"Evaluation complete: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
