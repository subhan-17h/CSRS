"""Offline tests for the Snort community-rules downloader."""

from __future__ import annotations

from scripts import fetch_snort_community_rules

RULES_TEXT = """\
# Snort community rules fixture

alert tcp any any -> any any ( msg:"first"; sid:1199; rev:18; )
alert udp any any -> any any ( msg:"second"; sid:43289; )
alert tcp any any -> any any ( msg:"duplicate"; sid:1199; rev:19; )
alert icmp any any -> any any ( msg:"missing sid"; rev:1; )
"""


def test_parse_rules_keeps_sid_rules_and_deduplicates_first() -> None:
    rules = fetch_snort_community_rules.parse_rules(RULES_TEXT)

    assert rules == (
        {
            "sid": "1199",
            "rule_text": 'alert tcp any any -> any any ( msg:"first"; sid:1199; rev:18; )',
        },
        {
            "sid": "43289",
            "rule_text": 'alert udp any any -> any any ( msg:"second"; sid:43289; )',
        },
    )


def test_render_document_has_exact_header_and_rule() -> None:
    rule = 'alert tcp any any -> any any ( msg:"first"; sid:1199; rev:18; )'

    rendered = fetch_snort_community_rules.render_document("1199", rule)

    assert rendered == (
        "SNORT RULE DOCUMENT | rule_id: 1:1199 | source: snort3-community.rules\n"
        "\n"
        f"{rule}\n"
    )


def test_write_rules_creates_one_atomic_document_per_rule(tmp_path) -> None:
    rules = fetch_snort_community_rules.parse_rules(RULES_TEXT)

    written, skipped, failed = fetch_snort_community_rules.write_rules(rules, tmp_path)

    assert (written, skipped, failed) == (2, 0, [])
    assert (tmp_path / "snort_rule_1-1199.txt").is_file()
    assert (tmp_path / "snort_rule_1-43289.txt").is_file()
    assert list(tmp_path.glob("*.partial")) == []
