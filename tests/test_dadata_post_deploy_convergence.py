from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_stage.sh"
DADATA = ROOT / "scripts" / "configure_dadata_stage.sh"


def test_stage_scripts_remain_valid_bash() -> None:
    for script in (DEPLOY, DADATA):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_main_deploy_preserves_existing_dadata_runtime_material() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "DADATA_API" in text
    assert "DADATA_SECRET" in text
    assert "DADATA_TOKEN" in text
    assert "DADATA_BACKOFF_BASE_SECONDS" in text
    assert "DADATA_BACKOFF_MAX_SECONDS" in text
    assert 'grep -E \'^(DADATA_API|DADATA_SECRET|DADATA_TOKEN|' in text
    assert "existing DaData material preserved" in text


def test_dadata_reconcile_only_recreates_on_real_material_change() -> None:
    text = DADATA.read_text(encoding="utf-8")
    compare_at = text.index('cmp -s "$tmp" "$RUNTIME_SECRETS_FILE"')
    change_flag_at = text.index("DADATA_RUNTIME_CHANGED=1", compare_at)
    conditional_at = text.index("if (( DADATA_RUNTIME_CHANGED == 1 )); then", change_flag_at)
    recreate_at = text.index('up -d --force-recreate "$SERVICE"', conditional_at)
    skip_at = text.index(
        "Auditor recreate skipped because DaData runtime material is unchanged",
        recreate_at,
    )

    assert compare_at < change_flag_at < conditional_at < recreate_at < skip_at
    assert text.count('up -d --force-recreate "$SERVICE"') == 1
    assert "DaData runtime credentials already match desired state; preserving running container" in text


def test_dadata_health_and_live_lookup_are_still_required_after_noop_reconcile() -> None:
    text = DADATA.read_text(encoding="utf-8")
    assert "/api/missions/registry-mirror/dadata/health" in text
    assert "/api/missions/registry-mirror/dadata/find-party" in text
    assert 'payload.get("state") == "active"' in text
    assert 'payload.get("secrets_exposed") is False' in text
    assert "DaData stage live smoke passed" in text
