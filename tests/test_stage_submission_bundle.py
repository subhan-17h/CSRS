import shutil
import subprocess
from pathlib import Path


def _write(path: Path, content: str = "fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="ascii")


def _make_fixture_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    cil = tmp_path / "CIL"
    repo = cil / "CSRS"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(
        Path(__file__).parents[1] / "scripts" / "stage_submission_bundle.sh",
        scripts / "stage_submission_bundle.sh",
    )

    for relative in (
        "project-docs/SUBMISSION_BUNDLE_README.md",
        "project-docs/SUBMISSION_EMAIL.md",
        "project-docs/PROJECT_WORK_HISTORY.md",
        "project-docs/DAY_INDEX.md",
        "CSRS_Work_Record.pdf",
        "CSRS_Presentation.pdf",
        "CSRS_Presentation.pptx",
        "RAG_Evaluation_Report.pdf",
        "results.md",
        "eval/final/report.md",
        "latex/figures/chart.pdf",
        "latex/figures/screenshot.png",
        "assets/screenshots/ui.png",
        "assets/architecture.svg",
    ):
        _write(repo / relative)

    for relative in (
        "alert_rankings_rag.json",
        "alert_ranking_rag_report.md",
        "alert_sample_50.json",
        "cretria.md",
        "alert_rag_run.jsonl",
        "alert_judge_run.jsonl",
        "parsed_alert_rag_fixture.json",
        "session_alert_rag_fixture.json",
        "archived/README.md",
    ):
        _write(cil / relative)

    for name in (
        "fetch_docs.py",
        "fetch_snort_community_rules.py",
        "fetch_snort_rule_docs.py",
        "build_snort_rule_docs.py",
        "run_alert_rag.py",
        "judge_alert_rankings.py",
        "build_alert_rag_report.py",
        "groq_llm.py",
        "warm_models.py",
    ):
        _write(scripts / name)

    return cil, repo, scripts


def test_stage_bundle_includes_powerpoint_deck(tmp_path: Path) -> None:
    """Catch a bundle build that ships the PDF deck but omits the required PPTX."""
    cil, repo, scripts = _make_fixture_repo(tmp_path)

    result = subprocess.run(
        ["bash", str(scripts / "stage_submission_bundle.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    staged = cil / "submission_bundle" / "02_presentation" / "CSRS_Presentation.pptx"
    assert staged.read_text(encoding="ascii") == "fixture"


def test_stage_bundle_fails_when_powerpoint_deck_is_missing(tmp_path: Path) -> None:
    """Catch a successful bundle build that cannot meet the instructor's PPTX requirement."""
    _, repo, scripts = _make_fixture_repo(tmp_path)
    (repo / "CSRS_Presentation.pptx").unlink()

    result = subprocess.run(
        ["bash", str(scripts / "stage_submission_bundle.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "CSRS_Presentation.pptx missing" in result.stderr
