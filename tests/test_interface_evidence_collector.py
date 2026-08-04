from __future__ import annotations

from app.capabilities.interface_audit.evidence_collector import _artifact, _sanitize_text
from app.capabilities.interface_audit.evidence_contract import InterfaceEvidenceManifest
from app.capabilities.interface_audit.rule_pack import load_rule_pack


def test_artifact_digest_is_deterministic():
    first = _artifact("dom.html", "text/html", b"<html></html>")
    second = _artifact("dom.html", "text/html", b"<html></html>")
    assert first.sha256 == second.sha256
    assert first.size_bytes == 13
    assert len(first.sha256) == 64


def test_sanitization_redacts_secrets_and_internal_paths():
    value = "Authorization: bearer-secret token=abc123 /opt/aimeton/runtime/file.json"
    sanitized = _sanitize_text(value)
    assert "bearer-secret" not in sanitized
    assert "abc123" not in sanitized
    assert "/opt/aimeton" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "[INTERNAL_PATH]" in sanitized


def test_manifest_binds_exact_rule_pack():
    rule_pack = load_rule_pack()
    artifact = _artifact("metadata.json", "application/json", b"{}")
    manifest = InterfaceEvidenceManifest(
        final_url="https://example.test/",
        title="Example",
        language="en",
        viewport={"width": 1440, "height": 900},
        color_scheme="light",
        reduced_motion="reduce",
        rule_pack_version=rule_pack.version,
        rule_pack_digest=rule_pack.digest,
        artifacts=(artifact,),
        console_messages=(),
        page_errors=(),
        failed_requests=(),
        redirects=(),
    )
    manifest.validate()
    assert manifest.rule_pack_version == "0.1.0"
    assert len(manifest.rule_pack_digest) == 64
