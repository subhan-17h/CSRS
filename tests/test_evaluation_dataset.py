"""Focused tests for the readable evaluation dataset and its validation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dataset import (
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    DatasetValidationError,
    GroundTruthDataset,
    load_corpus_manifest,
    load_dataset,
    validate_dataset,
    verify_evidence,
    verify_manifest,
    verify_unique_questions,
)


def test_readable_dataset_loads_twenty_questions() -> None:
    dataset = load_dataset()

    assert dataset.version == 1
    assert dataset.review_status == "draft"
    assert len(dataset.questions) == 20
    assert dataset.questions[0].reference_answers == [
        dataset.questions[0].answer,
        *dataset.questions[0].acceptable_answers,
    ]


def test_dataset_is_pretty_json() -> None:
    text = DEFAULT_DATASET.read_text(encoding="utf-8")
    raw = json.loads(text)

    assert text.startswith('{\n  "version": 1,\n')
    assert "\n    {\n      \"id\":" in text
    assert raw["questions"][0]["claims"][0] == {
        "id": "claim-1",
        "text": "GOVERN is a CSF Core Function.",
    }


def test_schema_rejects_missing_evidence() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["evidence"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        GroundTruthDataset.model_validate(raw)


def test_schema_rejects_fields_removed_from_minimal_format() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["question_type"] = "list"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GroundTruthDataset.model_validate(raw)


def test_duplicate_question_is_visible() -> None:
    dataset = load_dataset()
    duplicate = dataset.questions[1].model_copy(
        update={
            "id": "duplicate-question",
            "question": dataset.questions[0].question,
        }
    )

    with pytest.raises(DatasetValidationError, match="duplicate question"):
        verify_unique_questions([dataset.questions[0], duplicate])


def test_near_duplicate_question_is_visible() -> None:
    dataset = load_dataset()
    original = dataset.questions[0]
    near_duplicate = original.model_copy(
        update={
            "id": "near-duplicate-question",
            "question": f"{original.question} today",
        }
    )

    with pytest.raises(DatasetValidationError, match="near-duplicate questions"):
        verify_unique_questions([original, near_duplicate])


def test_manifest_hash_mismatch_is_visible() -> None:
    manifest = load_corpus_manifest()
    bad_entry = manifest.documents[0].model_copy(update={"sha256": "0" * 64})
    bad_manifest = manifest.model_copy(
        update={"documents": [bad_entry, *manifest.documents[1:]]}
    )

    with pytest.raises(DatasetValidationError, match="SHA-256 mismatch"):
        verify_manifest(bad_manifest)


def test_wrong_evidence_page_is_visible() -> None:
    dataset = load_dataset()
    manifest = load_corpus_manifest()
    question = dataset.questions[0]
    bad_evidence = question.evidence[0].model_copy(update={"pdf_page_index": 0})
    bad_question = question.model_copy(update={"evidence": [bad_evidence]})
    by_path = {entry.document_path: entry for entry in manifest.documents}

    with pytest.raises(DatasetValidationError, match="printed_page"):
        verify_evidence([bad_question], by_path)


def test_default_dataset_validates_against_corpus_and_index() -> None:
    dataset = validate_dataset(DEFAULT_DATASET, DEFAULT_MANIFEST)

    assert len(dataset.questions) == 20
    assert all(question.claims and question.evidence for question in dataset.questions)
    assert {
        evidence.document_path
        for question in dataset.questions
        for evidence in question.evidence
    } == {
        "docs/NIST.SP.1299.pdf",
        "docs/NIST.SP.800-53r5.pdf",
        "docs/samples/NIST.CSWP.29_CSF-2.0.pdf",
        "docs/samples/OWASP_Top_10_2021.txt",
    }


def test_default_paths_exist() -> None:
    assert Path(DEFAULT_DATASET).is_file()
    assert Path(DEFAULT_MANIFEST).is_file()
