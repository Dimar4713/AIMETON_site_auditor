from app.evidence_crawler.targeted_api import (
    IdentityGuardState,
    TargetedCrawlRequest,
    _guard,
)


def test_targeted_crawl_request_keeps_plan_optional():
    request = TargetedCrawlRequest()
    assert request.plan is None
    assert request.identity_result_id is None


def test_identity_guard_accepts_matching_strong_identifier():
    state = _guard(
        {"inn": ["2400000009"], "ogrn": ["1022400000006"]},
        {"inn": ["2400000009"]},
    )
    assert state == IdentityGuardState.ALIGNED


def test_identity_guard_blocks_another_company_identifier():
    state = _guard(
        {"inn": ["2400000009"], "ogrn": ["1022400000006"]},
        {"inn": ["2465000007"]},
    )
    assert state == IdentityGuardState.CONFLICTING


def test_identity_guard_reports_missing_anchor_without_false_alignment():
    state = _guard(
        {
            "inn": ["2400000009"],
            "legal_name": ["ооо дедал"],
        },
        {"legal_name": ["ооо другая компания"]},
    )
    assert state == IdentityGuardState.NOT_OBSERVED
