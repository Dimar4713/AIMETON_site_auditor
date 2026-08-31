from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "burst-runner-parallel-acceptance.yml"
ROUTER = ROOT / "scripts" / "aimeton_command_router.py"


def test_burst_parallel_acceptance_requires_two_dedicated_burst_jobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "max-parallel: 2" in text
    assert "slot: [1, 2]" in text
    assert "runs-on: [self-hosted, Linux, X64, stage, auditor, burst]" in text
    assert "scripts/verify_runner_contract_runtime.py" in text
    assert "--require-source burst" in text
    assert "scripts/validate_runner_contract_projection.py" in text
    assert "--list-source', 'burst'" in text
    assert "if set(runners) != expected" in text
    assert "aimeton-auditor-burst-stage-0[12]" not in text
    assert "sleep 20" in text
    assert "len(set(runners)) != 2" in text
    assert "max(starts) < min(ends)" in text


def test_burst_parallel_acceptance_has_no_private_reusable_workflow():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "uses: Dimar4713/aimeton-infrastructure/" not in text
    assert "uses: actions/" not in text
    assert "AIMETON_EXPECTED_PROJECTION_SHA256" in text
    assert "aimeton-control/runner-projection-sync" in text
    assert "canonical freshness authority" in text
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


def test_projection_validation_uses_github_hosted_runner():
    text = (ROOT / ".github" / "workflows" / "runner-contract-projection-validation.yml").read_text()
    assert "runs-on: ubuntu-latest" in text
    assert "aimeton-infrastructure/.github/workflows" not in text


def test_owner_only_command_uses_canonical_router():
    text = ROUTER.read_text(encoding="utf-8")
    assert '"accept-burst-parallel-stage": (' in text
    assert '783, "burst-runner-parallel-acceptance.yml"' in text
    assert '{"expected_sha": "{sha}", "evidence_issue": "783"}' in text
    assert "actor != OWNER" in text
