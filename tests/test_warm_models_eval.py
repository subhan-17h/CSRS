"""Focused tests for evaluation model prewarming."""

from __future__ import annotations

import runpy
from pathlib import Path

import huggingface_hub


def test_warm_bertscore_uses_pinned_snapshot_and_offline_cache_first(
    tmp_path: Path,
    monkeypatch,
) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "warm_models.py"
    namespace = runpy.run_path(str(script))
    calls: list[dict[str, object]] = []

    def snapshot_download(**kwargs: object) -> str:
        calls.append(kwargs)
        if kwargs["local_files_only"]:
            raise FileNotFoundError("not cached")
        return str(tmp_path)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot_download)

    assert namespace["warm_bertscore"]()
    assert [call["local_files_only"] for call in calls] == [True, False]
    assert {call["revision"] for call in calls} == {
        "722cf37b1afa9454edce342e7895e588b6ff1d59"
    }
    assert all("model.safetensors" in call["allow_patterns"] for call in calls)
