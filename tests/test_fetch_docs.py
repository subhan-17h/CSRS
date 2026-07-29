"""Tests for the durable single-document fetch workflow."""

from __future__ import annotations

from scripts import fetch_docs


def test_fetch_sources_contain_only_csf_sample() -> None:
    assert [source.filename for source in fetch_docs.SOURCES] == [
        "NIST.CSWP.29_CSF-2.0.pdf"
    ]


def test_fetch_skips_existing_sample_without_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_docs, "SAMPLES_DIR", tmp_path)
    target = tmp_path / fetch_docs.SOURCES[0].filename
    target.write_bytes(b"%PDF-existing")
    monkeypatch.setattr(
        fetch_docs,
        "_get",
        lambda url: (_ for _ in ()).throw(AssertionError("network should not be used")),
    )

    status, size = fetch_docs.fetch(fetch_docs.SOURCES[0], force=False)

    assert status == "skipped (committed sample already present)"
    assert size == len(b"%PDF-existing")


def test_force_refreshes_same_sample_path_atomically(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_docs, "SAMPLES_DIR", tmp_path)
    source = fetch_docs.SOURCES[0]
    payload = b"%PDF-" + b"x" * source.min_bytes
    monkeypatch.setattr(fetch_docs, "_get", lambda url: payload)

    status, size = fetch_docs.fetch(source, force=True)

    assert status == "downloaded"
    assert size == len(payload)
    assert (tmp_path / source.filename).read_bytes() == payload
    assert not (tmp_path / f"{source.filename}.partial").exists()
