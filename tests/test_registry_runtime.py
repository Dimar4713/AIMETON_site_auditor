from datetime import UTC, datetime

import pytest

from app.entity_resolution.models import (
    CandidateIdentifier,
    IdentityCandidate,
    IdentityCandidateState,
    IdentitySignalRef,
    SignalValidationState,
)
from app.entity_resolution.registry import (
    EntityRelationshipRole,
    RegistryAuthority,
    RegistryEvidence,
    RegistryVerificationState,
)
from app.entity_resolution.registry_runtime import (
    HumanReviewDecision,
    RegistryVerificationCoordinator,
)


DIGEST = f"sha256:{'a' * 64}"


def _ref(kind: str, value: str) -> IdentitySignalRef:
    return IdentitySignalRef(
        kind=kind,
        value=value,
        normalized_value=value.casefold(),
        validation_state=SignalValidationState.VALID,
        document_id="document_first_party",
        source_url="https://example.test/requisites",
        locator=f"body/{kind}",
        accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
        document_digest=DIGEST,
    )


def _candidate() -> IdentityCandidate:
    return IdentityCandidate(
        id="identity_candidate_test",
        entity_type="company",
        canonical_name='ООО "Дедал"',
        confidence=0.95,
        state=IdentityCandidateState.PROVISIONAL,
        identifiers=[
            CandidateIdentifier(
                scheme="legal_name",
                value='ООО "Дедал"',
                normalized_value="ооо дедал",
                signal_refs=[_ref("legal_name", 'ООО "Дедал"')],
            ),
            CandidateIdentifier(
                scheme="inn",
                value="2400000009",
                normalized_value="2400000009",
                signal_refs=[_ref("inn", "2400000009")],
            ),
            CandidateIdentifier(
                scheme="ogrn",
                value="1022400000006",
                normalized_value="1022400000006",
                signal_refs=[_ref("ogrn", "1022400000006")],
            ),
        ],
    )


def _evidence(*, role=EntityRelationshipRole.SUBJECT, inn="2400000009"):
    return RegistryEvidence(
        id=f"registry_evidence_{role.value}_{inn}",
        authority=RegistryAuthority.FNS_EGRUL,
        source_url="https://egrul.nalog.ru/",
        locator="registry-record/1",
        accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
        document_digest=DIGEST,
        legal_name='ООО "Дедал"',
        inn=inn,
        ogrn="1022400000006",
        relationship_role=role,
    )


def test_exact_authority_result_can_promote():
    coordinator = RegistryVerificationCoordinator()
    result = coordinator.verify("mission_test", _candidate(), [_evidence()])

    assert result.state == RegistryVerificationState.VERIFIED
    assert len(result.accepted_identifier_ids) == 2
    assert coordinator.can_promote(result)
    assert coordinator.history("mission_test").results == [result]


def test_relationship_scope_creates_append_only_review_decision():
    coordinator = RegistryVerificationCoordinator()
    result = coordinator.verify(
        "mission_test",
        _candidate(),
        [_evidence(), _evidence(role=EntityRelationshipRole.BRANCH)],
    )

    assert result.state == RegistryVerificationState.REVIEW_REQUIRED
    assert result.human_review is not None
    assert not coordinator.can_promote(result)

    decision = coordinator.decide(
        "mission_test",
        result.human_review.id,
        decision=HumanReviewDecision.REQUEST_MORE_EVIDENCE,
        reviewer="operator@example.test",
        note="Нужна выписка по филиалу.",
    )
    assert decision.decision == HumanReviewDecision.REQUEST_MORE_EVIDENCE
    assert coordinator.history("mission_test").decisions == [decision]

    assert coordinator.decide(
        "mission_test",
        result.human_review.id,
        decision=HumanReviewDecision.REQUEST_MORE_EVIDENCE,
        reviewer="operator@example.test",
        note="Нужна выписка по филиалу.",
    ) == decision

    with pytest.raises(ValueError, match="append-only"):
        coordinator.decide(
            "mission_test",
            result.human_review.id,
            decision=HumanReviewDecision.ACCEPT,
            reviewer="operator@example.test",
        )


def test_authoritative_mismatch_remains_non_promotable_even_after_review_record():
    coordinator = RegistryVerificationCoordinator()
    result = coordinator.verify(
        "mission_test",
        _candidate(),
        [_evidence(inn="2400000015")],
    )

    assert result.state == RegistryVerificationState.CONFLICTING
    assert "authoritative_inn_mismatch" in result.conflicts
    assert result.human_review is not None
    assert not coordinator.can_promote(result)

    coordinator.decide(
        "mission_test",
        result.human_review.id,
        decision=HumanReviewDecision.REJECT,
        reviewer="operator@example.test",
    )
    assert not coordinator.can_promote(result)
