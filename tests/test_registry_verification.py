from __future__ import annotations

from datetime import UTC, datetime

from app.entity_resolution.models import (
    CandidateIdentifier,
    IdentityCandidate,
    IdentityCandidateState,
    IdentitySignalRef,
    SignalValidationState,
)
from app.entity_resolution.registry import (
    EntityRelationshipRole,
    OfficialRegistryVerifier,
    RegistryAuthority,
    RegistryEvidence,
    RegistryVerificationState,
)


DIGEST = f"sha256:{'a' * 64}"
NOW = datetime(2026, 7, 30, tzinfo=UTC)


def _signal(kind: str, value: str) -> IdentitySignalRef:
    return IdentitySignalRef(
        kind=kind,
        value=value,
        normalized_value=value,
        validation_state=SignalValidationState.VALID,
        document_id=f"document_{kind}",
        source_url="https://example.test/requisites",
        locator=f"body/{kind}",
        accessed_at=NOW,
        document_digest=DIGEST,
    )


def _candidate() -> IdentityCandidate:
    return IdentityCandidate(
        id="identity_candidate_dedal",
        entity_type="company",
        canonical_name='ООО "Дедал"',
        confidence=0.95,
        state=IdentityCandidateState.PROVISIONAL,
        identifiers=[
            CandidateIdentifier(
                scheme="legal_name",
                value='ООО "Дедал"',
                normalized_value="ооо дедал",
                signal_refs=[_signal("legal_name", "ооо дедал")],
            ),
            CandidateIdentifier(
                scheme="inn",
                value="2400000009",
                normalized_value="2400000009",
                signal_refs=[_signal("inn", "2400000009")],
            ),
            CandidateIdentifier(
                scheme="ogrn",
                value="1022400000006",
                normalized_value="1022400000006",
                signal_refs=[_signal("ogrn", "1022400000006")],
            ),
        ],
    )


def _evidence(**overrides) -> RegistryEvidence:
    payload = {
        "id": "registry_evidence_dedal",
        "authority": RegistryAuthority.FNS_EGRUL,
        "source_url": "https://egrul.nalog.ru/",
        "locator": "record/1022400000006",
        "accessed_at": NOW,
        "document_digest": DIGEST,
        "legal_name": 'Общество с ограниченной ответственностью "Дедал"',
        "inn": "2400000009",
        "ogrn": "1022400000006",
    }
    payload.update(overrides)
    return RegistryEvidence(**payload)


def test_exact_official_registry_match_is_verified():
    result = OfficialRegistryVerifier().verify(_candidate(), [_evidence()])

    assert result.state == RegistryVerificationState.VERIFIED
    assert result.authority == RegistryAuthority.FNS_EGRUL
    assert len(result.accepted_identifier_ids) == 2
    assert result.conflicts == []
    assert result.gaps == []
    assert result.human_review is None
    assert {item.scheme for item in result.identifier_checks if item.matched} == {
        "inn",
        "ogrn",
    }


def test_authoritative_identifier_mismatch_is_fail_closed():
    result = OfficialRegistryVerifier().verify(
        _candidate(),
        [_evidence(inn="7700000000", id="registry_evidence_other")],
    )

    assert result.state == RegistryVerificationState.CONFLICTING
    assert "authoritative_inn_mismatch" in result.conflicts
    assert result.accepted_identifier_ids == []
    assert result.gaps == ["human_identity_review"]
    assert result.human_review is not None
    assert "authoritative_inn_mismatch" in result.human_review.reason_codes


def test_branch_or_affiliate_record_never_verifies_subject_automatically():
    result = OfficialRegistryVerifier().verify(
        _candidate(),
        [
            _evidence(
                id="registry_evidence_branch",
                relationship_role=EntityRelationshipRole.BRANCH,
            )
        ],
    )

    assert result.state == RegistryVerificationState.REVIEW_REQUIRED
    assert result.accepted_identifier_ids == []
    assert result.human_review is not None
    assert "registry_subject_record_missing" in result.human_review.reason_codes
    assert "registry_relationship_scope_requires_review" in (
        result.human_review.reason_codes
    )


def test_missing_registry_evidence_is_explicitly_unresolved():
    result = OfficialRegistryVerifier().verify(_candidate(), [])

    assert result.state == RegistryVerificationState.UNRESOLVED
    assert result.gaps == ["official_registry_evidence_missing"]
    assert result.accepted_identifier_ids == []
