"""Load and validate the readable evidence-grounded evaluation dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = Path(__file__).with_name("data") / "ground_truth.json"
DEFAULT_MANIFEST = Path(__file__).with_name("data") / "corpus_manifest.json"
NEAR_DUPLICATE_THRESHOLD = 0.90


class DatasetValidationError(Exception):
    """A dataset defect with enough context for an author to correct it."""


class Claim(BaseModel):
    """One atomic fact required for a complete answer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str

    @field_validator("id", "text")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class Evidence(BaseModel):
    """One exact source passage supporting the reference answer."""

    model_config = ConfigDict(extra="forbid")

    document_path: str
    section: str | None
    printed_page: str | None
    pdf_page_index: int | None = Field(ge=0)
    text: str

    @field_validator("document_path", "text")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class Question(BaseModel):
    """One answerable evaluation question."""

    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    answer: str
    acceptable_answers: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)

    @field_validator("id", "question", "answer")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("id")
    @classmethod
    def stable_id(cls, value: str) -> str:
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", value) is None:
            raise ValueError("must be a lowercase, hyphen-separated stable ID")
        return value

    @field_validator("acceptable_answers")
    @classmethod
    def valid_alternates(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("must not contain empty answers")
        return values

    @model_validator(mode="after")
    def unique_content(self) -> Question:
        """Reject repeated answers, claim IDs/text, and evidence entries."""
        answer_keys = [
            normalize_text(answer).casefold()
            for answer in [self.answer, *self.acceptable_answers]
        ]
        if len(answer_keys) != len(set(answer_keys)):
            raise ValueError("reference and acceptable answers must be unique")

        claim_ids = [claim.id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique within a question")
        claim_keys = [normalize_text(claim.text).casefold() for claim in self.claims]
        if len(claim_keys) != len(set(claim_keys)):
            raise ValueError("claim text must be unique within a question")

        evidence_keys = [
            (
                item.document_path,
                item.pdf_page_index,
                normalize_text(item.text).casefold(),
            )
            for item in self.evidence
        ]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("evidence entries must be unique within a question")
        return self

    @property
    def reference_answers(self) -> list[str]:
        """Return the primary answer followed by accepted alternatives."""
        return [self.answer, *self.acceptable_answers]


class GroundTruthDataset(BaseModel):
    """Versioned human-readable dataset envelope."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    review_status: Literal["draft"]
    questions: list[Question] = Field(min_length=1)


class ManifestEntry(BaseModel):
    """One source document recorded in the corpus manifest."""

    model_config = ConfigDict(extra="forbid")

    document_path: str
    document_title: str
    document_version: str | None
    sha256: str
    page_count: int | None = Field(ge=1)
    extraction_status: Literal["extracted"]
    page_numbering_ambiguity: str | None

    @field_validator("document_path", "document_title")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("sha256")
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("must be a lowercase SHA-256 digest")
        return value


class CorpusManifest(BaseModel):
    """Versioned corpus manifest envelope."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    documents: list[ManifestEntry] = Field(min_length=1)

    @field_validator("documents")
    @classmethod
    def unique_paths(cls, documents: list[ManifestEntry]) -> list[ManifestEntry]:
        paths = [document.document_path for document in documents]
        if len(paths) != len(set(paths)):
            raise ValueError("document paths must be unique")
        return documents


def normalize_text(text: str) -> str:
    """Normalize extraction whitespace without deleting meaningful content."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"(?<=\w)-\s+(?=\w)", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalized_question(question: str) -> str:
    """Return a conservative lexical duplicate-detection key."""
    return re.sub(r"[^a-z0-9]+", " ", question.casefold()).strip()


def lexical_tokens(text: str) -> set[str]:
    """Return case-insensitive alphanumeric tokens for extraction-aware matching."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return set(re.findall(r"[a-z0-9]+", normalized))


def file_sha256(path: Path) -> str:
    """Hash one source file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_dataset(path: Path = DEFAULT_DATASET) -> GroundTruthDataset:
    """Load the pretty JSON dataset and validate its schema."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return GroundTruthDataset.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
        raise DatasetValidationError(f"dataset is invalid: {error}") from error


def load_corpus_manifest(path: Path = DEFAULT_MANIFEST) -> CorpusManifest:
    """Load the corpus manifest and validate its schema."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return CorpusManifest.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
        raise DatasetValidationError(f"manifest is invalid: {error}") from error


def resolve_source(relative_path: str) -> Path:
    """Resolve a canonical repository-relative source without permitting traversal."""
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.as_posix() != relative_path:
        raise DatasetValidationError(
            f"source must be a canonical repository-relative POSIX path: {relative_path}"
        )
    source = (PROJECT_ROOT / candidate).resolve()
    docs_root = (PROJECT_ROOT / "docs").resolve()
    if not source.is_relative_to(docs_root):
        raise DatasetValidationError(f"source must be under docs/: {relative_path}")
    if source.relative_to(PROJECT_ROOT).as_posix() != relative_path:
        raise DatasetValidationError(f"source path is not canonical: {relative_path}")
    if not source.is_file():
        raise DatasetValidationError(f"source does not exist: {relative_path}")
    return source


def verify_manifest(manifest: CorpusManifest) -> dict[str, ManifestEntry]:
    """Verify manifest sources, hashes, page counts, extraction, and live index identity."""
    by_path: dict[str, ManifestEntry] = {}
    for entry in manifest.documents:
        source = resolve_source(entry.document_path)
        actual_hash = file_sha256(source)
        if actual_hash != entry.sha256:
            raise DatasetValidationError(
                f"{entry.document_path}: SHA-256 mismatch: {actual_hash}"
            )

        suffix = source.suffix.casefold()
        if suffix == ".pdf":
            reader = PdfReader(source)
            if entry.page_count != len(reader.pages):
                raise DatasetValidationError(
                    f"{entry.document_path}: page count is {len(reader.pages)}, "
                    f"manifest says {entry.page_count}"
                )
            empty_pages = [
                index
                for index, page in enumerate(reader.pages)
                if not normalize_text(page.extract_text() or "")
            ]
            if empty_pages:
                raise DatasetValidationError(
                    f"{entry.document_path}: pages without extracted text: {empty_pages}"
                )
        elif suffix == ".txt":
            if entry.page_count is not None:
                raise DatasetValidationError(
                    f"{entry.document_path}: TXT page_count must be null"
                )
            if not normalize_text(source.read_text(encoding="utf-8")):
                raise DatasetValidationError(
                    f"{entry.document_path}: text extraction is empty"
                )
        else:
            raise DatasetValidationError(
                f"{entry.document_path}: unsupported corpus format"
            )
        by_path[entry.document_path] = entry

    from csrs.config import settings
    from csrs.loaders import iter_document_paths
    from csrs.store import load_manifest as load_index_manifest

    discovered = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in iter_document_paths(settings.docs_dir)
    }
    if set(by_path) != discovered:
        raise DatasetValidationError(
            "manifest paths do not exactly match the supported corpus: "
            f"missing={sorted(discovered - set(by_path))}, "
            f"extra={sorted(set(by_path) - discovered)}"
        )

    indexed = load_index_manifest(settings.manifest_path)
    expected = {
        Path(path).relative_to("docs").as_posix(): entry
        for path, entry in by_path.items()
    }
    if set(indexed) != set(expected):
        raise DatasetValidationError(
            "live index manifest does not cover the same corpus as the dataset manifest"
        )
    for identity, entry in expected.items():
        index_record = indexed[identity]
        if (
            index_record["hash"] != entry.sha256
            or index_record["page_count"] != entry.page_count
        ):
            raise DatasetValidationError(
                f"{entry.document_path}: live index hash or page count is stale"
            )
    return by_path


def verify_unique_questions(questions: list[Question]) -> None:
    """Reject duplicate IDs, duplicate questions, and close paraphrase duplicates."""
    seen_ids: dict[str, int] = {}
    seen_questions: dict[str, tuple[int, str]] = {}
    normalized: list[tuple[str, str]] = []
    for position, question in enumerate(questions, start=1):
        if question.id in seen_ids:
            raise DatasetValidationError(
                f"duplicate ID {question.id!r} at positions "
                f"{seen_ids[question.id]} and {position}"
            )
        seen_ids[question.id] = position

        key = normalized_question(question.question)
        if key in seen_questions:
            original_position, original_id = seen_questions[key]
            raise DatasetValidationError(
                f"duplicate question for {original_id} and {question.id} "
                f"at positions {original_position} and {position}"
            )
        seen_questions[key] = (position, question.id)
        normalized.append((question.id, key))

    for index, (left_id, left_text) in enumerate(normalized):
        for right_id, right_text in normalized[index + 1 :]:
            similarity = SequenceMatcher(None, left_text, right_text).ratio()
            if similarity >= NEAR_DUPLICATE_THRESHOLD:
                raise DatasetValidationError(
                    f"near-duplicate questions {left_id} and {right_id}: "
                    f"similarity={similarity:.3f}"
                )


def verify_evidence(
    questions: list[Question],
    manifest: dict[str, ManifestEntry],
) -> Counter[str]:
    """Verify evidence metadata and normalized exact spans against source pages."""
    source_counts: Counter[str] = Counter()
    pdf_cache: dict[str, PdfReader] = {}
    text_cache: dict[str, str] = {}

    for question in questions:
        question_sources: set[str] = set()
        for evidence in question.evidence:
            if evidence.document_path not in manifest:
                raise DatasetValidationError(
                    f"{question.id}: evidence source is absent from the manifest: "
                    f"{evidence.document_path}"
                )
            source = resolve_source(evidence.document_path)
            if source.suffix.casefold() == ".pdf":
                if evidence.pdf_page_index is None:
                    raise DatasetValidationError(
                        f"{question.id}: PDF evidence requires pdf_page_index"
                    )
                reader = pdf_cache.get(evidence.document_path)
                if reader is None:
                    reader = PdfReader(source)
                    pdf_cache[evidence.document_path] = reader
                if evidence.pdf_page_index >= len(reader.pages):
                    raise DatasetValidationError(
                        f"{question.id}: pdf_page_index "
                        f"{evidence.pdf_page_index} is out of range"
                    )
                extracted = reader.pages[evidence.pdf_page_index].extract_text() or ""
                if evidence.printed_page is not None and re.search(
                    rf"\b{re.escape(evidence.printed_page)}\b",
                    normalize_text(extracted),
                ) is None:
                    raise DatasetValidationError(
                        f"{question.id}: printed_page {evidence.printed_page!r} "
                        f"was not found on PDF page index {evidence.pdf_page_index}"
                    )
            else:
                if evidence.pdf_page_index is not None or evidence.printed_page is not None:
                    raise DatasetValidationError(
                        f"{question.id}: TXT evidence cannot have page identifiers"
                    )
                if evidence.document_path not in text_cache:
                    text_cache[evidence.document_path] = source.read_text(encoding="utf-8")
                extracted = text_cache[evidence.document_path]

            if normalize_text(evidence.text) not in normalize_text(extracted):
                raise DatasetValidationError(
                    f"{question.id}: evidence text was not found in "
                    f"{evidence.document_path} at page index {evidence.pdf_page_index}"
                )
            question_sources.add(evidence.document_path)

        source_counts.update(question_sources)
    return source_counts


def verify_index_mapping(questions: list[Question]) -> None:
    """Verify each evidence location and token set against the live chunk index."""
    from csrs.store import ChunkStore

    chunks = ChunkStore().all_chunks()
    if not chunks:
        raise DatasetValidationError("the live index contains no chunks")

    text_by_page: dict[tuple[str, int | None], list[str]] = {}
    for chunk in chunks:
        text_by_page.setdefault((chunk.doc_name, chunk.page), []).append(chunk.text)

    for question in questions:
        for evidence in question.evidence:
            doc_name = Path(evidence.document_path).name
            if evidence.pdf_page_index is not None:
                physical_page = evidence.pdf_page_index + 1
                indexed_text = " ".join(
                    text_by_page.get((doc_name, physical_page), [])
                )
                if not indexed_text:
                    raise DatasetValidationError(
                        f"{question.id}: no indexed chunk maps to {doc_name} "
                        f"physical page {physical_page}"
                    )
                missing = lexical_tokens(evidence.text) - lexical_tokens(indexed_text)
                if missing:
                    raise DatasetValidationError(
                        f"{question.id}: indexed page is missing evidence tokens: "
                        f"{sorted(missing)}"
                    )
                continue

            indexed_text = " ".join(
                text
                for (indexed_name, _), texts in text_by_page.items()
                if indexed_name == doc_name
                for text in texts
            )
            if normalize_text(evidence.text) not in normalize_text(indexed_text):
                raise DatasetValidationError(
                    f"{question.id}: TXT evidence was not found in indexed chunks "
                    f"for {doc_name}"
                )


def validate_dataset(
    dataset_path: Path = DEFAULT_DATASET,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> GroundTruthDataset:
    """Run all schema, corpus, evidence, duplicate, and index checks."""
    dataset = load_dataset(dataset_path)
    manifest = verify_manifest(load_corpus_manifest(manifest_path))
    verify_unique_questions(dataset.questions)
    verify_evidence(dataset.questions, manifest)
    verify_index_mapping(dataset.questions)
    return dataset


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse optional compatible dataset and manifest paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the configured files and return a shell-friendly status."""
    args = parse_args(argv)
    try:
        dataset = validate_dataset(args.dataset, args.manifest)
    except (DatasetValidationError, OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    source_counts = Counter(
        source
        for question in dataset.questions
        for source in {evidence.document_path for evidence in question.evidence}
    )
    print("Ground-truth dataset mechanically valid")
    print("Semantic claim support remains draft pending human review")
    print(f"questions: {len(dataset.questions)}")
    for source, count in sorted(source_counts.items()):
        print(f"  {source}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
