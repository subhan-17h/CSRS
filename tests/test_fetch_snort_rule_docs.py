"""Offline tests for the Snort rule-documentation downloader."""

from __future__ import annotations

import pytest
from scripts import fetch_snort_rule_docs


@pytest.fixture
def rule_page_html() -> str:
    """Return a compact fixture shaped like a real Snort rule-doc page."""
    return """
        <html>
          <head>
            <title>Snort - Rule Docs 1:1199</title>
            <style>.hidden { display: none; }</style>
            <script>window.secretJsTextMustNotAppear = true;</script>
          </head>
          <body>
            <nav>
              <a href="/">Snort</a>
              <a href="/users/sign_in">Sign In</a>
            </nav>
            <section><div>Rule Doc Search</div></section>
            <main>
              <h1>Rule Document 1:1199</h1>
              <h2>Rule Documentation</h2>
              <h3>Rule Category</h3>
              <p>SERVER-WEBAPP</p>
              <h3>Alert Message</h3>
              <p>SERVER-WEBAPP Compaq Insight directory traversal</p>
              <h3>Rule Explanation</h3>
              <p>This rule looks for attempts to exploit a directory traversal vulnerability.</p>
              <h3>What To Look For</h3>
              <p>Requests containing parent-directory path segments.</p>
              <h3>Known Usage</h3>
              <p>Observed against vulnerable Compaq Insight servers.</p>
              <h3>False Positives</h3>
              <p>No known false positives.</p>
              <h3>Contributors</h3>
              <p>Snort community</p>
              <h3>Rule Groups</h3>
              <p>Community rules</p>
              <h3>CVE</h3>
              <p>CVE-1999-0771</p>
              <h3>Rule Vulnerability</h3>
              <p>Directory Traversal</p>
              <h3>References</h3>
              <p>CVE database reference</p>
              <h3>MITRE Details</h3>
              <p>T1190 Exploit Public-Facing Application</p>
            </main>
            <footer>
              <a href="/privacy">Privacy Policy</a>
              <span>Copyright Snort</span>
            </footer>
          </body>
        </html>
    """


def test_extract_rule_text_keeps_content_and_removes_chrome(rule_page_html: str) -> None:
    text = fetch_snort_rule_docs.extract_rule_text(rule_page_html, gid=1, sid=1199)

    assert "Alert Message" in text
    assert "SERVER-WEBAPP Compaq Insight directory traversal" in text
    assert "CVE-1999-0771" in text
    assert "secretJsTextMustNotAppear" not in text
    assert "Privacy Policy" not in text
    assert "Sign In" not in text


def test_rendered_document_has_exact_header(rule_page_html: str, tmp_path) -> None:
    url = "https://www.snort.org/rule_docs/1-1199"
    source = fetch_snort_rule_docs.RuleSource(gid=1, sid=1199, url=url)
    rule_text = fetch_snort_rule_docs.extract_rule_text(rule_page_html, gid=1, sid=1199)
    rendered = fetch_snort_rule_docs.render_document(source, rule_text).encode("utf-8")
    target = tmp_path / source.filename

    fetch_snort_rule_docs._write(target, rendered)

    assert source.filename == "snort_rule_doc_1-1199.txt"
    first_line = target.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == (
        "SNORT RULE DOCUMENT | rule_id: 1:1199 | "
        "source: https://www.snort.org/rule_docs/1-1199"
    )
    assert not target.with_suffix(".txt.partial").exists()


def test_collect_rule_sources_deduplicates_urls() -> None:
    first_url = "https://www.snort.org/rule_docs/1-1199"
    second_url = "https://www.snort.org/rule_docs/1-25520"
    sample = {
        "entries": [
            {"rule_documentation": {"doc_url": first_url}},
            {"rule_documentation": {"doc_url": first_url}},
            {"rule_documentation": {"doc_url": second_url}},
            {"rule_documentation": {}},
        ]
    }

    sources = fetch_snort_rule_docs.collect_rule_sources(sample)

    assert len(sources) == 2
    assert {source.url for source in sources} == {first_url, second_url}


def test_parse_url_extracts_gid_and_sid() -> None:
    url = "https://www.snort.org/rule_docs/1-25520"

    assert fetch_snort_rule_docs.parse_url(url) == (1, 25520)
