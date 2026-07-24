#!/usr/bin/env python3
"""Prepare every model the application needs for fully offline use."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from csrs.config import settings
from csrs.model_names import canonical_model_name

DOCLING_REQUIRED_FILES = (
    Path("docling-project--docling-layout-heron/model.safetensors"),
    Path(
        "docling-project--docling-models/model_artifacts/tableformer/accurate/"
        "tableformer_accurate.safetensors"
    ),
)


def _directory_size(path: Path) -> int:
    """Return the total size of regular files below path."""
    if not path.is_dir():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _docling_ready(path: Path) -> bool:
    """Return whether the layout and table weights used by the parser are present."""
    return all((path / relative).is_file() for relative in DOCLING_REQUIRED_FILES)


def warm_docling() -> bool:
    """Download Docling's non-OCR parser weights when they are absent."""
    path = settings.docling_artifacts_path.expanduser()
    print("Docling models:")
    print(f"  path: {path}")

    if _docling_ready(path):
        print(f"  {_directory_size(path):,} bytes  [skipped (already present)]\n")
        return True

    executable = shutil.which("docling-tools")
    if executable is None:
        print("  FAILED: `docling-tools` is unavailable; install the Docling dependency.\n")
        return False

    print("  downloading layout and tableformer weights (OCR is not needed)...")
    result = subprocess.run(  # noqa: S603
        [
            executable,
            "models",
            "download",
            "--output-dir",
            str(path),
            "layout",
            "tableformer",
        ],
        check=False,
    )
    size = _directory_size(path)
    if result.returncode != 0:
        print(f"  {size:,} bytes  [FAILED: downloader exited {result.returncode}]\n")
        return False
    if not _docling_ready(path):
        print(f"  {size:,} bytes  [FAILED: required weights are still missing]\n")
        return False

    print(f"  {size:,} bytes  [downloaded]\n")
    return True


def warm_flashrank() -> bool:
    """Download and verify the configured FlashRank model weights."""
    path = settings.flashrank_cache_dir.expanduser()
    model_path = path / settings.flashrank_model
    print("FlashRank model:")
    print(f"  path: {model_path}")

    try:
        from flashrank import Ranker
        from flashrank.Config import model_file_map
    except ImportError:
        print("  FAILED: FlashRank is unavailable; run `uv sync`.\n")
        return False

    model_file = model_file_map.get(settings.flashrank_model)
    if model_file is None:
        print(f"  FAILED: unsupported model {settings.flashrank_model!r}.\n")
        return False

    weights_path = model_path / model_file
    already_present = weights_path.is_file()
    try:
        Ranker(
            model_name=settings.flashrank_model,
            cache_dir=str(path),
            log_level="WARNING",
        )
    except Exception as exc:
        print(f"  FAILED: could not prepare the model: {exc}\n")
        return False

    size = _directory_size(model_path)
    if not weights_path.is_file():
        print(f"  {size:,} bytes  [FAILED: required weights are still missing]\n")
        return False

    status = "skipped (already present)" if already_present else "downloaded"
    print(f"  {size:,} bytes  [{status}]\n")
    return True


def _required_ollama_models() -> tuple[str, ...]:
    """Return configured model names once each, in application order."""
    return tuple(dict.fromkeys((settings.embed_model, *settings.supported_llms)))


def warm_ollama(pull: bool) -> tuple[bool, int, int]:
    """Report Ollama model state and optionally pull missing models."""
    print("Ollama models:")
    print(f"  host: {settings.ollama_host}")

    try:
        import ollama
    except ImportError:
        print("  FAILED: the Ollama Python client is unavailable; run `uv sync`.\n")
        return False, 0, len(_required_ollama_models())

    client = ollama.Client(host=settings.ollama_host)
    try:
        response = client.list()
    except OSError as exc:
        print(f"  FAILED: Ollama is unreachable at {settings.ollama_host}: {exc}")
        print("  Start it with `ollama serve`, then run this script again.\n")
        return False, 0, len(_required_ollama_models())
    except (ollama.RequestError, ollama.ResponseError) as exc:
        print(f"  FAILED: Ollama could not list models: {exc}\n")
        return False, 0, len(_required_ollama_models())

    installed = {
        canonical_model_name(model.model)
        for model in response.models
        if model.model is not None
    }
    required = _required_ollama_models()
    missing = [name for name in required if canonical_model_name(name) not in installed]

    for name in required:
        status = "missing" if name in missing else "present"
        print(f"  {name}  [{status}]")

    if missing and not pull:
        print("\n  Missing models are not pulled automatically. Run:")
        for name in missing:
            print(f"    ollama pull {name}")

    pull_failures = 0
    if missing and pull:
        print()
        for name in missing:
            print(f"  Pulling {name}...")
            try:
                client.pull(name)
            except OSError as exc:
                print(f"    FAILED: Ollama is unreachable: {exc}")
                print("    Start it with `ollama serve`, then run this script again.")
                pull_failures += 1
            except (ollama.RequestError, ollama.ResponseError) as exc:
                print(f"    FAILED: {exc}")
                pull_failures += 1
            else:
                print("    pulled")

    remaining = len(missing) if not pull else pull_failures
    present = len(required) - remaining
    print()
    return remaining == 0, present, len(required)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pull-ollama",
        action="store_true",
        help="pull missing Ollama models (downloads may be several GB)",
    )
    args = parser.parse_args()

    print("Preparing model weights for offline use\n")
    docling_ok = warm_docling()
    flashrank_ok = warm_flashrank()
    ollama_ok, ollama_present, ollama_total = warm_ollama(args.pull_ollama)

    print("Summary:")
    print(f"  Docling: {'ready' if docling_ok else 'not ready'}")
    print(f"  FlashRank: {'ready' if flashrank_ok else 'not ready'}")
    print(f"  Ollama: {ollama_present} of {ollama_total} required models present")

    if not docling_ok or not flashrank_ok or not ollama_ok:
        print("\nRequired model weights are missing or could not be verified.")
        return 1
    print("\nAll required model weights are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
