from app.mission_checkpoint import MissionCheckpoint, checkpoint_digest, decide_resume


def checkpoint(**overrides):
    values = dict(
        mission_id="mission-1",
        sequence=3,
        phase="evidence_fetch",
        state_digest=checkpoint_digest({"phase": "evidence_fetch", "cursor": 2}),
        document_ids=("doc-2", "doc-1"),
        evidence_ids=("ev-2", "ev-1"),
    )
    values.update(overrides)
    return MissionCheckpoint(**values)


def test_checkpoint_digest_is_stable_for_equivalent_state():
    assert checkpoint_digest({"b": 2, "a": 1}) == checkpoint_digest({"a": 1, "b": 2})


def test_resume_only_creates_missing_documents_and_evidence():
    decision = decide_resume(
        checkpoint(),
        persisted_sequence=2,
        persisted_state_digest=None,
        existing_document_ids={"doc-1"},
        existing_evidence_ids={"ev-1"},
    )
    assert decision.status == "resume"
    assert decision.reason_code == "checkpoint_accepted"
    assert decision.next_sequence == 3
    assert decision.create_documents == ("doc-2",)
    assert decision.create_evidence == ("ev-2",)


def test_repeating_same_resume_is_idempotent():
    item = checkpoint()
    decision = decide_resume(
        item,
        persisted_sequence=item.sequence,
        persisted_state_digest=item.state_digest,
        existing_document_ids={"doc-1", "doc-2"},
        existing_evidence_ids={"ev-1", "ev-2"},
    )
    assert decision.status == "already_applied"
    assert decision.reason_code == "checkpoint_already_applied"
    assert decision.create_documents == ()
    assert decision.create_evidence == ()


def test_same_sequence_with_different_digest_fails_closed():
    decision = decide_resume(
        checkpoint(),
        persisted_sequence=3,
        persisted_state_digest="0" * 64,
        existing_document_ids=set(),
        existing_evidence_ids=set(),
    )
    assert decision.status == "blocked"
    assert decision.reason_code == "checkpoint_conflict"


def test_newer_persisted_state_is_not_replayed():
    decision = decide_resume(
        checkpoint(),
        persisted_sequence=4,
        persisted_state_digest=None,
        existing_document_ids=set(),
        existing_evidence_ids=set(),
    )
    assert decision.status == "already_applied"
    assert decision.next_sequence == 4
