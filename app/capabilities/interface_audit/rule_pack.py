from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ALLOWED_AUTHORITIES = {"standard", "aimeton_policy", "best_practice", "heuristic"}
_ALLOWED_SEVERITIES = {"low", "medium", "high"}
_REQUIRED_RULE_FIELDS = {
    "rule_id",
    "rule_version",
    "domain",
    "authority",
    "severity",
    "source",
    "rationale",
}


class RulePackError(ValueError):
    """Raised when a rule pack violates the fail-closed contract."""


@dataclass(frozen=True)
class LoadedRulePack:
    version: str
    digest: str
    manifest: dict[str, Any]
    rules: tuple[dict[str, Any], ...]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_rule(rule: dict[str, Any], seen_ids: set[str]) -> None:
    missing = sorted(_REQUIRED_RULE_FIELDS - rule.keys())
    if missing:
        raise RulePackError(f"rule missing required fields: {', '.join(missing)}")

    rule_id = rule["rule_id"]
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise RulePackError("rule_id must be a non-empty string")
    if rule_id in seen_ids:
        raise RulePackError(f"duplicate rule_id: {rule_id}")
    seen_ids.add(rule_id)

    if rule["authority"] not in _ALLOWED_AUTHORITIES:
        raise RulePackError(f"unsupported authority for {rule_id}: {rule['authority']}")
    if rule["severity"] not in _ALLOWED_SEVERITIES:
        raise RulePackError(f"unsupported severity for {rule_id}: {rule['severity']}")

    for field in ("rule_version", "domain", "source", "rationale"):
        if not isinstance(rule[field], str) or not rule[field].strip():
            raise RulePackError(f"{field} must be a non-empty string for {rule_id}")


def load_rule_pack(base_dir: Path | None = None) -> LoadedRulePack:
    root = base_dir or Path(__file__).with_name("rule_packs") / "v0.1"
    manifest_path = root / "manifest.json"
    rules_path = root / "rules.json"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rules_document = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RulePackError(f"cannot load rule pack: {exc}") from exc

    version = manifest.get("rule_pack_version")
    if not isinstance(version, str) or not version.strip():
        raise RulePackError("manifest.rule_pack_version must be a non-empty string")
    if rules_document.get("rule_pack_version") != version:
        raise RulePackError("manifest and rules rule_pack_version mismatch")

    rules = rules_document.get("rules")
    if not isinstance(rules, list) or not rules:
        raise RulePackError("rules must be a non-empty list")

    seen_ids: set[str] = set()
    normalized_rules: list[dict[str, Any]] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            raise RulePackError("every rule must be an object")
        _validate_rule(raw_rule, seen_ids)
        normalized_rules.append(raw_rule)

    digest_payload = {
        "manifest": manifest,
        "rules": {"rule_pack_version": version, "rules": normalized_rules},
    }
    digest = hashlib.sha256(_canonical_json(digest_payload)).hexdigest()
    return LoadedRulePack(
        version=version,
        digest=digest,
        manifest=manifest,
        rules=tuple(normalized_rules),
    )
