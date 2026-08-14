import pytest

from app.search_gap_query_replay import GapQueryReplayCase, ReplaySearchResult


def case(**updates):
    base = dict(
        mission_id="m1",
        attempt_id="a1",
        gap_code="sparse_yield",
        effective_regime="balanced",
        suggested_follow_up_query="стоматология Красноярск контакты",
        observed_query="  Стоматология   Красноярск КОНТАКТЫ ",
        baseline_domains=["known.example"],
        results=[],
    )
    base.update(updates)
    return GapQueryReplayCase(**base)


def test_query_identity_must_match_suggestion():
    with pytest.raises(ValueError, match="gap_query_replay_query_mismatch"):
        case(observed_query="другой запрос").to_retained_outcome()


def test_replay_derives_new_unique_and_quality_evidence():
    outcome = case(results=[
        ReplaySearchResult(url="https://known.example/a", qualified=True),
        ReplaySearchResult(url="https://new.example/a", qualified=True, direct_or_official=True),
        ReplaySearchResult(url="https://new.example/b", qualified=True),
    ]).to_retained_outcome()
    evidence = outcome.evidence
    assert evidence.added_raw_results == 3
    assert evidence.added_unique_domains == 1
    assert evidence.duplicate_results == 1
    assert evidence.added_qualified_candidates == 3
    assert evidence.added_direct_or_official_candidates == 1


def test_discovery_without_explicit_novelty_labels_stays_unscorable():
    retained = case(
        gap_code="discovery_novelty_unmeasured",
        effective_regime="discovery",
        results=[ReplaySearchResult(url="https://new.example")],
    ).to_retained_outcome()
    assessment = retained.assess()
    assert assessment.verdict == "not_scorable"


def test_discovery_explicit_novelty_can_be_supported():
    retained = case(
        gap_code="discovery_novelty_unmeasured",
        effective_regime="discovery",
        results=[ReplaySearchResult(url="https://rare.example", novel_entity=True, rare_hit=False)],
    ).to_retained_outcome()
    assessment = retained.assess()
    assert assessment.verdict == "supported"


def test_routing_changed_replay_is_rejected():
    with pytest.raises(ValueError, match="gap_query_replay_requires_routing_unchanged"):
        case(routing_changed=True).to_retained_outcome()
