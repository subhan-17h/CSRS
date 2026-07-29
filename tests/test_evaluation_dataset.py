"""Focused tests for the readable evaluation dataset and its validation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dataset import (
    CSF_DOCUMENT_PATH,
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    EXPECTED_APPENDIX_FUNCTION_COUNTS,
    EXPECTED_QUESTION_TYPE_COUNTS,
    EXPECTED_TOPIC_COUNTS,
    DatasetValidationError,
    GroundTruthDataset,
    load_corpus_manifest,
    load_dataset,
    missing_index_tokens,
    validate_dataset,
    verify_evidence,
    verify_manifest,
    verify_unique_questions,
)


def test_readable_dataset_loads_csf_only_fifty_question_benchmark() -> None:
    dataset = load_dataset()

    assert dataset.version == 2
    assert dataset.review_status == "draft"
    assert len(dataset.questions) == 50
    assert dataset.questions[0].reference_answers == [
        dataset.questions[0].answer,
        *dataset.questions[0].acceptable_answers,
    ]
    assert all(
        len(question.claims) == 1
        if question.question_type == "direct"
        else len(question.claims) >= 2
        for question in dataset.questions
    )


def test_manifest_is_version_two_and_csf_only() -> None:
    manifest = load_corpus_manifest()

    assert manifest.version == 2
    assert len(manifest.documents) == 1
    assert manifest.documents[0].document_path == CSF_DOCUMENT_PATH


def test_dataset_is_pretty_json() -> None:
    text = DEFAULT_DATASET.read_text(encoding="utf-8")
    raw = json.loads(text)

    assert text.startswith('{\n  "version": 2,\n')
    assert "\n    {\n      \"id\":" in text
    assert raw["questions"][0]["topic"] == "overview_applicability"


def test_schema_rejects_missing_evidence() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["evidence"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        GroundTruthDataset.model_validate(raw)


def test_schema_rejects_unknown_fields() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["difficulty"] = "easy"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GroundTruthDataset.model_validate(raw)


def test_schema_enforces_coverage_and_question_type_quotas() -> None:
    dataset = load_dataset()

    topic_counts = {
        topic: sum(question.topic == topic for question in dataset.questions)
        for topic in EXPECTED_TOPIC_COUNTS
    }
    type_counts = {
        question_type: sum(
            question.question_type == question_type
            for question in dataset.questions
        )
        for question_type in EXPECTED_QUESTION_TYPE_COUNTS
    }
    appendix_counts = {
        function: sum(
            question.topic == "appendix_a"
            and question.id.startswith(f"appendix-a-{function}-")
            for question in dataset.questions
        )
        for function in EXPECTED_APPENDIX_FUNCTION_COUNTS
    }

    assert topic_counts == EXPECTED_TOPIC_COUNTS
    assert type_counts == EXPECTED_QUESTION_TYPE_COUNTS
    assert appendix_counts == EXPECTED_APPENDIX_FUNCTION_COUNTS


def test_schema_rejects_wrong_topic_quota() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["topic"] = "core_functions"

    with pytest.raises(ValidationError, match="topic counts must be"):
        GroundTruthDataset.model_validate(raw)


def test_schema_rejects_non_csf_evidence_source() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["evidence"][0]["document_path"] = "docs/other.pdf"

    with pytest.raises(ValidationError, match="evidence must use only"):
        GroundTruthDataset.model_validate(raw)


def test_schema_rejects_non_csf_section_name() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["questions"][0]["evidence"][0]["section"] = "Introduction"

    with pytest.raises(ValidationError, match="invalid CSF sections"):
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


def test_index_token_coverage_accepts_only_adjacent_word_joins() -> None:
    assert missing_index_tokens(
        "high-level security and T he organization",
        "highlevel security and The organization",
    ) == set()
    assert missing_index_tokens(
        "high-level security requirement",
        "highlevel privacy requirement",
    ) == {"security"}


def test_manifest_hash_mismatch_is_visible() -> None:
    manifest = load_corpus_manifest()
    bad_entry = manifest.documents[0].model_copy(update={"sha256": "0" * 64})
    bad_manifest = manifest.model_copy(update={"documents": [bad_entry]})

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

    assert len(dataset.questions) == 50
    assert all(question.claims and question.evidence for question in dataset.questions)
    assert {
        evidence.document_path
        for question in dataset.questions
        for evidence in question.evidence
    } == {CSF_DOCUMENT_PATH}


def test_default_paths_exist() -> None:
    assert Path(DEFAULT_DATASET).is_file()
    assert Path(DEFAULT_MANIFEST).is_file()
