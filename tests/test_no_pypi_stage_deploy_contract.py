from pathlib import Path


def test_stage_deploy_does_not_install_from_pypi() -> None:
    workflow = Path('.github/workflows/deploy-stage.yml').read_text(encoding='utf-8')
    forbidden = (
        'pip install',
        'requirements-openstack.txt',
        'openstacksdk',
        'pypi.org',
    )
    for token in forbidden:
        assert token not in workflow


def test_stage_provider_policy_enables_free_tier_contour() -> None:
    workflow = Path('.github/workflows/deploy-stage.yml').read_text(encoding='utf-8')
    assert "yandex,tavily,searxng" in workflow
    assert "IDENTITY_SEARCH_ALLOW_PAID_FALLBACK" in workflow
    assert "SEARCH_QUOTA_TAVILY" in workflow
    assert "SEARCH_QUOTA_YANDEX" in workflow
