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
verifier = _load("verify_runner_contract_runtime", ROOT / "scripts" / "verify_runner_contract_runtime.py")


def _projection_and_digest():
    projection = projection_module.load_projection()
    return projection, projection["generation"]["canonical_projection_sha256"]


def test_generated_projection_has_exact_canonical_provenance():
    projection, digest = _projection_and_digest()
    generation = projection["generation"]
    assert generation["infrastructure_repository"] == "Dimar4713/aimeton-infrastructure"
    assert len(generation["infrastructure_source_sha"]) == 40
    assert len(digest) == 64
    assert {source["path"] for source in generation["sources"]} == {
        "ops/main-server/runners.json",
        "ops/burst-runner/site-auditor-runners.json",
        "ops/burst-runner/repository-pools.json",
    }


@pytest.mark.parametrize("runner_name", ["aimeton-auditor-burst-stage-01", "aimeton-auditor-burst-stage-02"])
def test_burst_acceptance_allows_each_canonically_proven_identity(runner_name):
    _, digest = _projection_and_digest()
    result = verifier.verify_runtime_identity(
        "site-auditor-stage", runner_name, require_source="burst", canonical_proof_sha256=digest
    )
    assert result["runner_source"] == "burst"
    assert result["identity_membership_verified"] is True
    assert result["runtime_labels_verified"] is False
    assert result["selector_authority"] == "github-scheduler"
    assert result["canonical_proof_verified"] is True


def test_missing_or_stale_canonical_proof_fails_closed():
    projection, _ = _projection_and_digest()
    for proof in (None, "0" * 64):
        with pytest.raises(projection_module.ProjectionError):
            projection_module.validate_projection_proof(projection, proof)


def test_burst_acceptance_rejects_persistent_and_unknown_identity():
    _, digest = _projection_and_digest()
    for runner_name in ("aimeton-site-auditor-stage", "unregistered-runner"):
        with pytest.raises(projection_module.ProjectionError):
            verifier.verify_runtime_identity(
                "site-auditor-stage", runner_name, require_source="burst", canonical_proof_sha256=digest
            )


def test_explicit_empty_runtime_labels_fail_closed():
    _, digest = _projection_and_digest()
    with pytest.raises(projection_module.ProjectionError, match="runtime labels"):
        verifier.verify_runtime_identity(
            "site-auditor-stage",
            "aimeton-auditor-burst-stage-01",
            actual_labels=[],
            require_source="burst",
            canonical_proof_sha256=digest,
        )


def test_payload_mutation_fails_local_digest_validation(tmp_path):
    projection, _ = _projection_and_digest()
    mutated = copy.deepcopy(projection)
    mutated["canonical_payload"]["contract"]["eligible_runners"][1]["runner_name"] = "drift"
    path = tmp_path / "projection.json"
    path.write_text(json.dumps(mutated))
    with pytest.raises(projection_module.ProjectionError, match="digest"):
        projection_module.load_projection(path)


def test_projection_has_no_independent_inventory_or_resolver():
    assert not (ROOT / "ops" / "runner-inventory.json").exists()
    assert not (ROOT / "scripts" / "resolve_runner_contract.py").exists()
