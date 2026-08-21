from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "burst-runner-parallel-acceptance.yml"
ROUTER = ROOT / "scripts" / "aimeton_command_router.py"


def test_burst_parallel_acceptance_requires_two_dedicated_burst_jobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "max-parallel: 2" in text
    assert "slot: [1, 2]" in text
    assert "runs-on: [self-hosted, Linux, X64, stage, auditor, burst]" in text
    assert "aimeton-auditor-burst-stage-0[12]" in text
    assert "sleep 20" in text
    assert "len(set(runners)) != 2" in text
    assert "max(starts) < min(ends)" in text


def test_burst_parallel_acceptance_is_provider_and_marketplace_free():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "uses:" not in text
    for forbidden in (
        "openstack",
        "routerai",
        "ROUTERAI_API_KEY",
        "create_server",
        "delete_server",
        "unshelve_server",
        "shelve_server",
    ):
        assert forbidden not in text
    assert "provider/model calls: `none`" in text
    assert "release authority: `none`" in text


def test_burst_parallel_acceptance_is_exact_main_pinned_and_evidence_scoped():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "expected_sha:" in text
    assert "test \"$current_main\" = \"$TARGET_SHA\"" in text
    assert 'test "$EVIDENCE_ISSUE" = "783"' in text
    assert "issues: write" in text
    assert "actions: read" in text


def test_owner_only_command_uses_canonical_router():
    text = ROUTER.read_text(encoding="utf-8")
    assert '"accept-burst-parallel-stage": (' in text
    assert '783, "burst-runner-parallel-acceptance.yml"' in text
    assert '{"expected_sha": "{sha}", "evidence_issue": "783"}' in text
    assert 'actor != OWNER' in text
    assert 're.fullmatch(r"/([a-z0-9-]+)\\s+([0-9a-f]{40})", body)' in text
