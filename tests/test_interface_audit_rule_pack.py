from pathlib import Path

import pytest

from app.capabilities.interface_audit.rule_pack import RulePackError, load_rule_pack


def test_bundled_rule_pack_is_deterministic() -> None:
    first = load_rule_pack()
    second = load_rule_pack()

    assert first.version == "0.1.0"
    assert first.digest == second.digest
    assert len(first.digest) == 64
    assert {rule["domain"] for rule in first.rules} == {
        "accessibility",
        "layout",
        "writing",
        "observability",
    }
    assert first.manifest["runtime_dependency_on_sources"] is False


def test_duplicate_rule_ids_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"rule_pack_version":"0.1.0"}', encoding="utf-8"
    )
    duplicated = (
        '{"rule_pack_version":"0.1.0","rules":['
        '{"rule_id":"DUP","rule_version":"1","domain":"layout",'
        '"authority":"heuristic","severity":"low","source":"test",'
        '"rationale":"test"},'
        '{"rule_id":"DUP","rule_version":"1","domain":"layout",'
        '"authority":"heuristic","severity":"low","source":"test",'
        '"rationale":"test"}]}'
    )
    (tmp_path / "rules.json").write_text(duplicated, encoding="utf-8")

    with pytest.raises(RulePackError, match="duplicate rule_id"):
        load_rule_pack(tmp_path)


def test_manifest_and_rules_version_mismatch_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"rule_pack_version":"0.1.0"}', encoding="utf-8"
    )
    (tmp_path / "rules.json").write_text(
        '{"rule_pack_version":"0.2.0","rules":[]}', encoding="utf-8"
    )

    with pytest.raises(RulePackError, match="version mismatch"):
        load_rule_pack(tmp_path)
