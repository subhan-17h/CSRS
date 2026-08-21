"""Offline tests for the Snort rule-document builder."""

from __future__ import annotations

import json

import pytest
from scripts import build_snort_rule_docs


def _record(**overrides: object) -> dict:
    record = {
        "gid": 1,
        "sid": 108,
        "rev": 1,
        "msg": "Community rule message",
        "classtype": "trojan-activity",
        "action": "alert",
        "protocol": "tcp",
        "src_net": "$HOME_NET",
        "src_port": "any",
        "dst_net": "$EXTERNAL_NET",
        "dst_port": "80",
        "flow": "to_server, established",
        "metadata": "service http",
        "content_matches": '"/cgi-bin/"',
        "doc_found": 1,
        "doc_url": "https://www.snort.org/rule_docs/1-108",
        "rule_text": (
            'alert tcp $HOME_NET any -> $EXTERNAL_NET 80 '
            '(msg:"Community rule message"; sid:108; rev:1;)'
        ),
        "direction_label": "outbound",
    }
    record.update(overrides)
    return record


def test_render_document_with_documentation_has_exact_sections() -> None:
    record = _record(
        rule_category="Browser Plugins",
        alert_message_doc="Documented alert message",
        rule_explanation="Detects a documented browser exploit.",
        contributors="Snort Research Team",
        cve_ids="CVE-2025-0001, CVE-2025-0002",
        cve_text="The vulnerability affects a browser plugin.",
        references_text="https://example.com/advisory",
        service="http",
    )

    rendered = build_snort_rule_docs.render_document(record)

    assert rendered == (
        "SNORT RULE DOCUMENT | rule_id: 1:108 | "
        "source: https://www.snort.org/rule_docs/1-108\n"
        "\n"
        "Rule Category\n"
        "Browser Plugins\n"
        "\n"
        "Alert Message\n"
        "Documented alert message\n"
        "\n"
        "Rule Explanation\n"
        "Detects a documented browser exploit.\n"
        "\n"
        "Rule Properties\n"
        "classtype: trojan-activity | action: alert | protocol: tcp | service: http\n"
        "flow: to_server, established | direction: outbound\n"
        "source: $HOME_NET:any -> destination: $EXTERNAL_NET:80\n"
        'content matches: "/cgi-bin/"\n'
        "metadata: service http\n"
        "\n"
        "CVE\n"
        "CVE-2025-0001, CVE-2025-0002\n"
        "The vulnerability affects a browser plugin.\n"
        "\n"
        "References\n"
        "https://example.com/advisory\n"
        "\n"
        "Contributors\n"
        "Snort Research Team\n"
        "\n"
        "Rule Text\n"
        'alert tcp $HOME_NET any -> $EXTERNAL_NET 80 '
        '(msg:"Community rule message"; sid:108; rev:1;)\n'
    )


def test_render_document_joins_list_valued_cve_ids() -> None:
    record = _record(cve_ids=["CVE-2025-0001", " ", "CVE-2025-0002"])

    rendered = build_snort_rule_docs.render_document(record)

    assert "\n\nCVE\nCVE-2025-0001, CVE-2025-0002\n\n" in rendered


def test_render_document_without_documentation_has_exact_minimal_sections() -> None:
    record = _record(
        sid=105,
        msg="Minimal alert message",
        doc_found=0,
        doc_url="",
        flow="",
        metadata="",
        content_matches="",
        direction_label="",
        rule_text='alert tcp any any -> any any (msg:"Minimal"; sid:105; rev:1;)',
    )

    rendered = build_snort_rule_docs.render_document(record)

    assert rendered == (
        "SNORT RULE DOCUMENT | rule_id: 1:105 | source: snort3-community.rules\n"
        "\n"
        "Alert Message\n"
        "Minimal alert message\n"
        "\n"
        "Rule Properties\n"
        "classtype: trojan-activity | action: alert | protocol: tcp\n"
        "source: $HOME_NET:any -> destination: $EXTERNAL_NET:80\n"
        "\n"
        "Rule Text\n"
        'alert tcp any any -> any any (msg:"Minimal"; sid:105; rev:1;)\n'
    )


def test_render_document_omits_empty_optional_fields_without_dangling_text() -> None:
    record = _record(
        rule_category=" ",
        service="",
        flow=" ",
        direction_label="",
        content_matches="",
        metadata=" ",
        cve_ids=[],
        cve_text="",
        references_text=" ",
        contributors="",
        rule_explanation="",
    )

    rendered = build_snort_rule_docs.render_document(record)

    assert "Rule Category\n" not in rendered
    assert "Rule Explanation\n" not in rendered
    assert "CVE\n" not in rendered
    assert "References\n" not in rendered
    assert "Contributors\n" not in rendered
    assert " | service:" not in rendered
    assert "flow:" not in rendered
    assert "content matches:" not in rendered
    assert "metadata:" not in rendered
    assert "\n\n\n" not in rendered


def test_render_document_handles_real_records_without_endpoint_keys() -> None:
    record = _record()
    for field in ("src_net", "src_port", "dst_net", "dst_port"):
        record.pop(field)

    rendered = build_snort_rule_docs.render_document(record)

    assert "\nsource:" not in rendered
    assert "destination:" not in rendered
    assert "Rule Properties\n" in rendered
    assert "classtype: trojan-activity | action: alert | protocol: tcp\n" in rendered
    assert "\n\n\n" not in rendered


def test_render_document_keeps_only_surviving_property_lines() -> None:
    flow_record = _record(
        flow="to_server",
        direction_label="",
        content_matches="",
        metadata="",
    )
    empty_record = _record(
        flow="",
        direction_label="",
        content_matches="",
        metadata="",
    )
    missing_fields = (
        "classtype",
        "action",
        "protocol",
        "src_net",
        "src_port",
        "dst_net",
        "dst_port",
    )
    for record in (flow_record, empty_record):
        for field in missing_fields:
            record.pop(field)

    flow_rendered = build_snort_rule_docs.render_document(flow_record)
    empty_rendered = build_snort_rule_docs.render_document(empty_record)

    assert "\n\nRule Properties\nflow: to_server\n\nRule Text\n" in flow_rendered
    assert "Rule Properties\n" not in empty_rendered


def test_render_document_falls_back_to_rule_message() -> None:
    rendered = build_snort_rule_docs.render_document(_record())

    assert "Alert Message\nCommunity rule message\n" in rendered


def test_write_documents_overwrites_atomically_with_required_filenames(tmp_path) -> None:
    records = (
        _record(sid=105, doc_found=0, rule_text="rule 105"),
        _record(sid=1000, doc_url="https://www.snort.org/rule_docs/1-1000"),
    )
    stale = tmp_path / "snort_rule_1-105.txt"
    stale.write_text("stale content", encoding="utf-8")

    result = build_snort_rule_docs.write_documents(records, tmp_path)

    assert result == (2, [])
    assert stale.read_text(encoding="utf-8") == build_snort_rule_docs.render_document(
        records[0]
    )
    assert (tmp_path / "snort_rule_1-1000.txt").read_text(
        encoding="utf-8"
    ) == build_snort_rule_docs.render_document(records[1])
    assert list(tmp_path.glob("*.partial")) == []


def test_load_records_sorts_by_integer_sid(tmp_path) -> None:
    source = tmp_path / "records.json"
    source.write_text(
        json.dumps(
            {
                "1000": _record(sid=1000),
                "105": _record(sid=105, doc_found=0),
            }
        ),
        encoding="utf-8",
    )

    records = build_snort_rule_docs.load_records(source)

    assert tuple(record["sid"] for record in records) == (105, 1000)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "JSON object"),
        ({}, "empty"),
        ({"108": {"gid": 1, "msg": "message", "rule_text": "rule"}}, "sid"),
        ({"108": {"sid": 108, "msg": "message", "rule_text": "rule"}}, "gid"),
        ({"108": {"sid": 108, "gid": 1, "rule_text": "rule"}}, "msg"),
        ({"108": {"sid": 108, "gid": 1, "msg": "message"}}, "rule_text"),
    ],
)
def test_load_records_rejects_invalid_input(tmp_path, payload, message) -> None:
    source = tmp_path / "records.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        build_snort_rule_docs.load_records(source)
