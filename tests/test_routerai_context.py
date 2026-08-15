from __future__ import annotations

from app.routerai_context import DISCOVERY_SNIPPET_CHARS, compact_routerai_sources


def test_compact_routerai_sources_preserves_all_source_ids_and_semantics() -> None:
    sources = [
        {
            "id": "H1",
            "title": "Discovery",
            "url": "https://example.test/one",
            "snippet": "x" * 900,
            "accessed_at": "2026-08-15T00:00:00Z",
            "query_kind": "finance",
            "result_kind": "finance",
            "source_class": "finance",
            "classification_state": "classified",
            "lifecycle_state": "discovery_hint",
            "verification_note": "repeated service text",
            "source_type": "finance",
            "evidence_level": "unverified_mention",
            "document_url": None,
            "document_digest": None,
            "evidence_quote": None,
        },
        {
            "id": "H2",
            "title": "Evidence",
            "url": "https://example.test/two",
            "snippet": "fallback",
            "accessed_at": "2026-08-15T00:00:00Z",
            "query_kind": "registry",
            "source_class": "registry",
            "lifecycle_state": "evidence",
            "source_type": "registry",
            "evidence_level": "corroborated_signal",
            "document_url": "https://example.test/document",
            "document_digest": "sha256:doc",
            "evidence_quote": "q" * 700,
            "evidence_digest": "sha256:evidence",
        },
    ]

    compact = compact_routerai_sources(sources)

    assert [item["id"] for item in compact] == ["H1", "H2"]
    assert compact[0]["query_kind"] == "finance"
    assert compact[0]["source_class"] == "finance"
    assert compact[0]["evidence_level"] == "unverified_mention"
    assert len(compact[0]["snippet"]) == DISCOVERY_SNIPPET_CHARS
    assert "verification_note" not in compact[0]
    assert "document_url" not in compact[0]

    assert compact[1]["lifecycle_state"] == "evidence"
    assert compact[1]["document_url"] == "https://example.test/document"
    assert compact[1]["document_digest"] == "sha256:doc"
    assert compact[1]["evidence_digest"] == "sha256:evidence"
    assert compact[1]["snippet"] == "q" * 700


def test_compaction_does_not_drop_sources() -> None:
    sources = [
        {
            "id": f"H{index}",
            "snippet": "signal" * 100,
            "query_kind": "other",
            "lifecycle_state": "discovery_hint",
        }
        for index in range(1, 61)
    ]

    compact = compact_routerai_sources(sources)

    assert len(compact) == 60
    assert {item["id"] for item in compact} == {f"H{index}" for index in range(1, 61)}
