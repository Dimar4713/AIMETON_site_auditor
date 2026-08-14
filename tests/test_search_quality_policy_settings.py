from pathlib import Path

from app.search_observer_quality_policy import QualityFirstPromotionPolicy
from app.search_quality_policy_settings import SearchQualityPolicyRepository


def test_search_quality_policy_round_trip(tmp_path: Path):
    db = tmp_path / "runtime.sqlite3"
    repo = SearchQualityPolicyRepository(db)
    policy = QualityFirstPromotionPolicy(
        max_qualified_yield_drop_ratio=0.05,
        max_direct_or_official_yield_drop_ratio=0.02,
        max_waste_ratio_increase=0.15,
        resource_policy_mode="existing_hard_caps",
    )

    saved = repo.save(policy, actor_id=7, reason=" tune search quality envelope ")
    loaded = repo.get()

    assert saved.policy == policy
    assert saved.updated_by == 7
    assert saved.reason == "tune search quality envelope"
    assert loaded == saved


def test_search_quality_policy_default_is_conservative(tmp_path: Path):
    record = SearchQualityPolicyRepository(tmp_path / "runtime.sqlite3").get()
    assert record.policy.max_qualified_yield_drop_ratio == 0.0
    assert record.policy.max_direct_or_official_yield_drop_ratio == 0.0
    assert record.policy.max_waste_ratio_increase == 0.0
    assert record.policy.resource_policy_mode == "existing_hard_caps"
