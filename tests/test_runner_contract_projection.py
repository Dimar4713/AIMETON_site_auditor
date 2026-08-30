import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


projection_module = _load(
    "validate_runner_contract_projection",
    ROOT / "scripts" / "validate_runner_contract_projection.py",
)
sys.modules["validate_runner_contract_projection"] = projection_module
verifier = _load(
    "verify_runner_contract_runtime",
    ROOT / "scripts" / "verify_runner_contract_runtime.py",
)


PERSISTENT = {
    "runners": [
        {
            "key": "auditor_stage",
            "repository": "Dimar4713/AIMETON_site_auditor",
            "name": "aimeton-site-auditor-stage",
            "labels": ["stage", "auditor"],
        }
    ]
}
BURST = {
    "runners": [
        {
            "key": "auditor_burst_stage_01",
            "repository": "Dimar4713/AIMETON_site_auditor",
            "name": "aimeton-auditor-burst-stage-01",
            "labels": ["stage", "auditor", "burst"],
        },
        {
            "key": "auditor_burst_stage_02",
            "repository": "Dimar4713/AIMETON_site_auditor",
            "name": "aimeton-auditor-burst-stage-02",
            "labels": ["stage", "auditor", "burst"],
        },
    ]
}


def test_generated_projection_matches_canonical_documents():
    projection = projection_module.load_projection()
    contract = projection_module.validate_projection_against_documents(
        projection, PERSISTENT, BURST
    )
    assert [runner["runner_name"] for runner in contract["eligible_runners"]] == [
        "aimeton-site-auditor-stage",
        "aimeton-auditor-burst-stage-01",
        "aimeton-auditor-burst-stage-02",
    ]


def test_projection_records_exact_canonical_provenance():
    generation = projection_module.load_projection()["generation"]
    assert generation["infrastructure_repository"] == "Dimar4713/aimeton-infrastructure"
    assert len(generation["infrastructure_source_sha"]) == 40
    assert {source["path"] for source in generation["sources"]} == {
        "ops/main-server/runners.json",
        "ops/burst-runner/site-auditor-runners.json",
    }
    assert all(len(source["git_blob_sha"]) == 40 for source in generation["sources"])


@pytest.mark.parametrize(
    "runner_name",
    ["aimeton-auditor-burst-stage-01", "aimeton-auditor-burst-stage-02"],
)
def test_burst_acceptance_allows_each_projected_identity(runner_name):
    result = verifier.verify_runtime_identity(
        "site-auditor-stage",
        runner_name,
        require_source="burst",
        validate_drift=False,
    )
    assert result["runner_source"] == "burst"
    assert result["identity_membership_verified"] is True
    assert result["runtime_labels_verified"] is False
    assert result["selector_authority"] == "github-scheduler"


def test_burst_acceptance_rejects_persistent_and_unknown_identity():
    for runner_name in ("aimeton-site-auditor-stage", "unregistered-runner"):
        with pytest.raises(projection_module.ProjectionError):
            verifier.verify_runtime_identity(
                "site-auditor-stage",
                runner_name,
                require_source="burst",
                validate_drift=False,
            )


def test_explicit_empty_runtime_labels_fail_closed():
    with pytest.raises(projection_module.ProjectionError, match="runtime labels"):
        verifier.verify_runtime_identity(
            "site-auditor-stage",
            "aimeton-auditor-burst-stage-01",
            actual_labels=[],
            require_source="burst",
            validate_drift=False,
        )


@pytest.mark.parametrize("field", ["name", "repository", "labels"])
def test_canonical_inventory_drift_fails_closed(field):
    burst = copy.deepcopy(BURST)
    burst["runners"][0][field] = "drift" if field != "labels" else ["stage"]
    with pytest.raises(projection_module.ProjectionError):
        projection_module.validate_projection_against_documents(
            projection_module.load_projection(), PERSISTENT, burst
        )


def test_projection_file_has_no_independent_inventory_or_resolver():
    assert not (ROOT / "ops" / "runner-inventory.json").exists()
    assert not (ROOT / "scripts" / "resolve_runner_contract.py").exists()
    payload = json.loads(
        (ROOT / "contracts" / "generated" / "runner-contract-projection.json").read_text()
    )
    assert payload["schema_version"] == "1.0-generated"
