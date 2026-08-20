# Semantic Verifier P0 — offline calibration scaffold

Status: **implemented in branch `feat/verifier-p0-offline`; live verifier backend not yet authorized/confirmed**.

Tracking:
- `Dimar4713/aimeton-architecture#123`
- `Dimar4713/AIMETON_site_auditor#783`
- AIMETON fork: `Dimar4713/llm-as-a-verifier`, working branch `aimeton/verifier-p0`

## Purpose

Prepare a reproducible Site Auditor calibration layer for a probabilistic semantic verifier without giving the verifier release authority and without requiring a network, model secret, or paid provider call.

The P0 scaffold uses the existing frozen `SEF-BENCHMARK-20` / `Golden-5` material because it already carries manually verified first-party facts and therefore gives AIMETON an external target against which verifier ranking can later be calibrated.

## Implemented offline state

`app/verifier_contract.py` defines provider-neutral `VerificationRequest` / `VerificationResult` models. They deliberately contain no types from `llm-verifier` or a model provider.

Hard invariants are encoded in the schema:
- `client_release_authority=false` in every request;
- `client_release_eligible=false` in every semantic result;
- `hard_gate_override=false` in every semantic result.

`app/verifier_fixtures.py` converts each Golden-5 case into five deterministic candidate classes:
- `correct`;
- `incomplete`;
- `unsupported`;
- `identity_conflicted`;
- `evidence_poor`.

The initial semantic criteria are factual correctness, evidence grounding, completeness and inference discipline. Release readiness is intentionally not an actionable criterion.

## Fork / engine status

The experimental fork carries two P0 protections before Site Auditor is allowed to depend on it:
- local fix + regression for upstream issue #14 (ring-pass scores lost when `cache=None`);
- AIMETON score-evidence guard that distinguishes valid score evidence from an upstream fallback `0.5` caused by missing signal.

The fork remains an experiment, not a standardized dependency. `Verifier != Truth` remains the controlling invariant.

## Control-plane validation gate

PR #784 remains fail-closed on repository Baseline evidence. During its offline implementation the older mixed-event Baseline workflow failed to register an exact-SHA validation job even though Acceptance Governance ran successfully on the same repository-scoped runner. Control-plane repair #785 therefore separated automatic `push`/`pull_request` Baseline validation from the owner-only exact-SHA dispatch workflow.

The verifier PR must be revalidated on a post-#785 head. A green semantic-verifier unit suite is not sufficient by itself: the repository Baseline must execute on `aimeton-site-auditor-stage`, preserve exact-SHA materialization and remain Marketplace-free. This control-plane proof does not authorize any live verifier/model/provider call.

## Next gate

Offline work can proceed through fixture generation, adapter mapping, calibration bookkeeping and replay preparation.

A live verifier run requires a separately confirmed backend that exposes usable token-level logprobs plus an authorized secret/budget where the endpoint is paid. Until then:
- no paid API calls;
- no production routing;
- no client-release effect;
- no weakening of Evidence Guard, MissionReleaseControl or mandatory human sign-off.
