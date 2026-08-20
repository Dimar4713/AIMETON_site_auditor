# VERIFIER-P0 live calibration

Status: experimental P0 evidence. This document does not change release, hard/evidence/policy, HITL, OCC-49, budget, or production authority.

## Qualified backend evidence

RouterAI `openai/gpt-4o-mini` was runtime-qualified by Site Auditor workflow run `32413075031` on exact Site Auditor SHA `a410c119aaf9c509c693aa2dfdf7513d794efe03`.

Observed sanitized evidence:
- HTTP 200;
- token-level logprobs present;
- top-logprobs present;
- A-T score token visible;
- non-degenerate distribution;
- 36 prompt + 2 completion = 38 total tokens;
- latency 1788 ms;
- estimated cost 0.000662 RUB;
- raw provider response not retained;
- semantic verifier has no client-release or hard-gate authority.

The post-merge Site Auditor Baseline CI run `32412960145` is also green on the same exact SHA.

## Golden-5 live calibration slice

The next experiment uses the pinned AIMETON fork `Dimar4713/llm-as-a-verifier` at exact revision `9cabf17e3644778893666b864aec924e740006ba` and the frozen Site Auditor Benchmark-20 / Golden-5 fixtures.

Each Golden-5 request contains five deterministic candidate classes:
- correct;
- incomplete;
- unsupported;
- identity-conflicted;
- evidence-poor.

The strong synthetic oracle only requires `correct` to outrank every deliberately damaged variant. It does not invent a total order among damaged variants.

## Execution guards

The live harness:
- is owner-dispatched from issue #783 only;
- is pinned to RouterAI `openai/gpt-4o-mini`;
- uses `n_evaluations=1`, `pivots=2`, `max_workers=1`, `on_error=raise`;
- clamps primary verifier output to 512 tokens through the OpenAI-compatible client wrapper;
- reserves 5 RUB from the owner-authorized ceiling and performs a conservative preflight before every provider call;
- requires the expected A-T score-distribution coverage for each tournament result;
- marks partial/missing score evidence as degraded rather than neutral 0.5 measurement;
- persists only sanitized rankings, scores, usage, calibration metrics, and provenance;
- never persists raw provider responses or full candidate payloads;
- cannot set client release eligibility or override hard/evidence/policy/release/HITL gates.

Poor semantic ranking is a valid calibration result. Missing/degraded score evidence is a technical failure and is excluded from usable measurement coverage.

## Promotion gate

No production routing follows automatically from Golden-5. After five usable measurements, compare pairwise accuracy, Top-1 accuracy, false-accept behavior, token/cost/latency and later heterogeneous-verifier results. Promotion requires separate evidence and architecture/product decisions.
