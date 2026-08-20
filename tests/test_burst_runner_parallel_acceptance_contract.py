from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "burst-runner-parallel-acceptance.yml"
COMMAND = ROOT / ".github" / "workflows" / "burst-runner-parallel-command.yml"


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


def test_owner_only_command_is_exact_main_scoped_and_marketplace_free():
    text = COMMAND.read_text(encoding="utf-8")
    assert "github.event.issue.number == 783" in text
    assert "github.event.comment.user.login == 'Dimar4713'" in text
    assert "/accept-burst-parallel-stage " in text
    assert "burst-runner-parallel-acceptance.yml/dispatches" in text
    assert "sha != current" in text
    assert "actions: write" in text
    assert "uses:" not in text
