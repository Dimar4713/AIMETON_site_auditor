from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from app.verifier_contract import (
    SEF_VERIFIER_CRITERIA,
    VerificationCandidate,
    VerificationRequest,
)


CANDIDATE_CLASSES = (
    "correct",
    "incomplete",
    "unsupported",
    "identity_conflicted",
    "evidence_poor",
)


def _case_candidate_id(case_id: str, variant: str) -> str:
    return f"{case_id}:{variant}"


def _copy_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return copy.deepcopy(facts)


def _build_candidates(case_id: str, facts: list[dict[str, Any]]) -> list[VerificationCandidate]:
    correct = {
        "variant": "correct",
        "identity_status": "resolved",
        "facts": _copy_facts(facts),
    }

    incomplete_facts = _copy_facts(facts[:-1] if len(facts) > 1 else facts)
    incomplete = {
        "variant": "incomplete",
        "identity_status": "resolved",
        "facts": incomplete_facts,
        "omission_declared": True,
    }

    unsupported_facts = _copy_facts(facts)
    if unsupported_facts:
        target = next(
            (fact for fact in unsupported_facts if fact.get("predicate") in {"inn", "ogrn", "legal_name"}),
            unsupported_facts[0],
        )
        target["value"] = f"UNSUPPORTED::{target.get('value', '')}"
        target["verification_status"] = "unsupported"
        target["source"] = None
    unsupported = {
        "variant": "unsupported",
        "identity_status": "resolved",
        "facts": unsupported_facts,
    }

    conflicted_facts = _copy_facts(facts)
    legal = next((fact for fact in facts if fact.get("predicate") == "legal_name"), None)
    if legal is not None:
        conflicted_facts.append(
            {
                "predicate": "legal_name",
                "value": f"CONFLICT::{legal.get('value', '')}",
                "verification_status": "conflict",
                "source": None,
            }
        )
    identity_conflicted = {
        "variant": "identity_conflicted",
        "identity_status": "conflicted",
        "facts": conflicted_facts,
    }

    evidence_poor_facts = _copy_facts(facts)
    for fact in evidence_poor_facts:
        fact["source"] = None
        fact["verification_status"] = "unproven"
    evidence_poor = {
        "variant": "evidence_poor",
        "identity_status": "resolved",
        "facts": evidence_poor_facts,
    }

    payloads = [correct, incomplete, unsupported, identity_conflicted, evidence_poor]
    return [
        VerificationCandidate(id=_case_candidate_id(case_id, payload["variant"]), payload=payload)
        for payload in payloads
    ]


def build_sef_verification_requests(
    benchmark_path: str | Path,
    golden_path: str | Path,
) -> list[VerificationRequest]:
    """Build deterministic offline verifier requests from frozen SEF data.

    Only cases present in Golden-5 are emitted.  The function performs no
    network/provider/LLM calls and never mutates the benchmark files.
    """
    benchmark = json.loads(Path(benchmark_path).read_text(encoding="utf-8"))
    golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))

    case_meta = {case["id"]: case for case in benchmark["cases"]}
    requests: list[VerificationRequest] = []

    for golden_case in golden["cases"]:
        case_id = golden_case["case_id"]
        meta = case_meta[case_id]
        requests.append(
            VerificationRequest(
                request_id=f"sef-verifier-p0:{case_id}",
                task=(
                    "Rank candidate company-profile results for factual correctness, "
                    "evidence grounding, completeness and inference discipline. "
                    "Semantic ranking is advisory only and cannot authorize client release."
                ),
                candidates=_build_candidates(case_id, golden_case["facts"]),
                criteria=SEF_VERIFIER_CRITERIA,
                metadata={
                    "benchmark_id": benchmark["benchmark_id"],
                    "benchmark_version": benchmark["version"],
                    "golden_version": golden["golden_version"],
                    "case_id": case_id,
                    "display_name": meta["display_name"],
                    "official_url": meta["official_url"],
                    "candidate_classes": list(CANDIDATE_CLASSES),
                },
            )
        )

    return requests
