"""Offline tests for the v2 alert RAG report builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import build_alert_rag_report

MODEL = "openai/gpt-oss-120b"
JUDGE_MODEL = "meta-llama/llama-3.3-70b-versatile"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sample_entry(alert_id: int, priority: int) -> dict[str, object]:
    return {
        "alert_id": alert_id,
        "alert": {
            "timestamp": f"2026-08-13T12:00:0{alert_id}Z",
            "alert_message": f"WEB-IIS malformed request attempt {alert_id}",
            "rule_id": "1:1199:18",
            "classification": "Web Application Attack",
            "priority": priority,
            "protocol": "TCP",
            "service": "HTTP",
            "source_ip": "192.0.2.10",
            "source_port": 50000 + alert_id,
            "destination_ip": "198.51.100.20",
            "destination_port": 8080,
            "direction": "source_to_destination",
            "packet_length": 417,
            "gid": 1,
            "sid": 1199,
            "rev": 18,
        },
        "rule_documentation": {
            "classtype": "web-application-attack",
            "rule_explanation": "Fixture rule documentation.",
        },
    }


def _chunk(document: str, control_id: str | None = None) -> dict[str, object]:
    return {
        "rank": 1,
        "id": f"{document}:1",
        "text": "Fixture evidence.",
        "document": document,
        "section": "Fixture section",
        "control_id": control_id,
        "physical_page": 1,
        "dense_cosine_score": 0.75,
        "rrf_score": 0.03,
        "rerank_score": None,
    }


def _snapshot_row(
    alert_id: int,
    *,
    parsed: dict[str, object] | None,
    chunks: list[dict[str, object]],
) -> dict[str, object]:
    status = "parsed" if parsed is not None else "failed"
    attempts = [
        {
            "content": json.dumps(parsed) if parsed is not None else "not valid json",
            "meta": {
                "done_reason": "stop",
                "prompt_eval_count": 120,
                "eval_count": 80,
            },
        }
    ]
    return {
        "schema_version": 1,
        "run_id": "fixture-run",
        "model": MODEL,
        "alert_id": alert_id,
        "query": f"malformed request {alert_id}",
        "system": "Return exactly one line of valid JSON.",
        "retry_reminder": None,
        "chunks": chunks,
        "attempts": attempts,
        "parsed": parsed,
        "status": status,
        "done_reasons": ["stop"],
    }


def test_main_builds_flat_v2_deliverable(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    results_path = tmp_path / "alert_rag_run.jsonl"
    sample_path = tmp_path / "alert_sample_50.json"
    judge_path = tmp_path / "alert_judge_run.jsonl"
    prior_path = tmp_path / "missing_prior.json"
    report_path = tmp_path / "alert_ranking_rag_report.md"
    deliverable_path = tmp_path / "alert_rankings_rag.json"
    manifest_path = tmp_path / "manifest.json"

    sample_path.write_text(
        json.dumps(
            {
                "entries": [
                    _sample_entry(1, priority=3),
                    _sample_entry(2, priority=1),
                    _sample_entry(3, priority=2),
                ]
            }
        ),
        encoding="utf-8",
    )
    parsed_match = {
        "model_rank": 1,
        "justification": (
            "The alert describes a direct web exploitation attempt. The retrieved rule "
            "evidence supports treating it as severe."
        ),
        "mismatch_explanation": "The attack wording outweighed the lower Snort priority.",
        "metrics_used": ["alert_message", "classification", "priority"],
        "matched_sid": 1199,
        "sid_evidence_document": "snort_rule_1-1199.txt",
    }
    parsed_without_sid = {
        "model_rank": 5,
        "justification": (
            "The alert contains limited impact evidence. No matching rule document was "
            "available in the retrieved context."
        ),
        "mismatch_explanation": None,
        "metrics_used": ["alert_message", "protocol", "service"],
        "matched_sid": None,
        "sid_evidence_document": None,
    }
    snort_chunk = _chunk("snort_rule_1-1199.txt")
    standard_chunk = _chunk("NIST_CSF_2.0.pdf", "PR.PS-04")
    _write_jsonl(
        results_path,
        [
            _snapshot_row(1, parsed=parsed_match, chunks=[snort_chunk, standard_chunk]),
            _snapshot_row(2, parsed=parsed_without_sid, chunks=[standard_chunk]),
            _snapshot_row(3, parsed=None, chunks=[snort_chunk, standard_chunk]),
        ],
    )
    _write_jsonl(
        judge_path,
        [
            {
                "model": MODEL,
                "alert_id": 1,
                "status": "parsed",
                "judge_model": JUDGE_MODEL,
                "verdict": {
                    "score": 0.8,
                    "reasoning": "The rank is defensible and the justification is complete.",
                },
            }
        ],
    )
    manifest_path.write_text(
        json.dumps(
            {
                "docs/samples/snort_rule_1-1199.txt": {
                    "chunk_count": 1,
                    "page_count": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "alert_mismatch_justifications.jsonl").write_text(
        "this stale file must never be read\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(build_alert_rag_report, "OUT", report_path)
    monkeypatch.setattr(build_alert_rag_report, "OUTJSON", deliverable_path)
    monkeypatch.setattr(build_alert_rag_report, "MANIFEST", manifest_path)
    monkeypatch.setattr(build_alert_rag_report, "DEFAULT_PRIOR", prior_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_alert_rag_report.py",
            "--results",
            str(results_path),
            "--sample",
            str(sample_path),
            "--judge-results",
            str(judge_path),
        ],
    )

    assert not hasattr(build_alert_rag_report, "DEFAULT_JUSTIFY")
    assert build_alert_rag_report.main() == 0

    deliverable = json.loads(deliverable_path.read_text(encoding="utf-8"))
    assert len(deliverable) == 3
    by_id = {row["alert_id"]: row for row in deliverable}
    shared_keys = {
        "alert_id",
        "rule_id",
        "alert_message",
        "snort_priority",
        "classification",
        "classtype",
        "query",
        "ranker_model",
    }
    parsed_keys = shared_keys | {
        "model_rank",
        "justification",
        "anchored_rank",
        "mismatch",
        "mismatch_explanation",
        "metrics_used",
        "sid_matching",
    }
    assert set(by_id[1]) == parsed_keys | {"judge"}
    assert set(by_id[2]) == parsed_keys
    assert set(by_id[3]) == shared_keys | {"status", "raw"}
    assert by_id[1]["sid_matching"] == {
        "snort_sid": 1199,
        "rag_matched_sid": 1199,
        "evidence_document": "snort_rule_1-1199.txt",
        "sid_match": True,
    }
    assert by_id[2]["sid_matching"]["sid_match"] is None
    assert by_id[1]["judge"] == {
        "model": JUDGE_MODEL,
        "score": 0.8,
        "reasoning": "The rank is defensible and the justification is complete.",
    }
    assert by_id[3]["status"] == "failed"
    assert by_id[3]["raw"] == ["not valid json"]

    report = report_path.read_text(encoding="utf-8")
    assert JUDGE_MODEL in report
    assert "sid_match" in report
    assert "Pipe-line" not in report
    assert "The attack wording outweighed the lower Snort priority." in report
    assert "(explanation missing)" in report
    assert "(judged 1/2 parsed rankings)" in report
    assert "sid match 1/50 (attempted on 1)" in capsys.readouterr().out
