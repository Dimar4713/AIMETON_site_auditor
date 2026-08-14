# Search / Research Governance milestone — 2026-08-14

## Purpose

This document records the current Site Auditor / Hunter implementation state after the search-regime, shadow refinement, admin quality-policy and promotion-readiness work. It is the project-local implementation record; the generalized architecture is maintained in `Dimar4713/aimeton-architecture`.

## Architecture references

Canonical architecture package in `aimeton-architecture`:

- `Docs/Search_Research_Governance.md` — navigation hub;
- `Docs/ADR/ADR-018_Search_Intent_Admin_Quality_Policy_and_Evidence_Gated_Steering.md` — accepted boundary;
- `Docs/Principles/AIMETON_Evidence_Driven_Search_and_Promotion_Principles.md` — normative cross-product principles;
- `Docs/Engineering_Practices/AIMETON_Search_Research_Engineering_Practices.md` — reusable best practices;
- `Docs/History_of_Development/2026-08-14_Site_Auditor_Search_Research_Governance.md` — architecture-level milestone record.

Architecture PR: `Dimar4713/aimeton-architecture#92`.

## Product contract

### User plane

The ordinary Hunter user selects a search goal/tactic, not technical quality coefficients:

| UI meaning | Internal regime |
|---|---|
| Auto — system chooses from observed state | `auto` |
| Крупная рыба — strongest candidates first | `precision` |
| Баланс — shortlist quality plus breadth | `balanced` |
| Золотой песок — deeper rare-find discovery | `discovery` |

Requested and effective regimes are retained separately so auto-resolution remains explainable.

### Admin plane

Technical quality thresholds are administrator settings. Current persisted policy covers:

- maximum qualified-yield drop;
- maximum direct/official-yield drop;
- maximum duplicate/excluded waste increase;
- resource policy mode tied to the existing hard-cap envelope.

Policy updates are protected by admin authorization + CSRF and retain update timestamp, actor and reason.

### Execution plane

`SearchGateway` remains deterministic execution authority.

Search Observer, auto-regime reasoning and gap-refinement logic are advisory/shadow until promotion evidence and a separate activation decision authorize bounded steering.

## Implemented milestones

### Regime-aware behavior

Implemented and merged:

- deterministic `auto` regime resolver;
- API requested/effective regime metadata;
- regime-specific utility evidence;
- regime-segmented calibration;
- requested/effective invariants;
- deterministic flat calibration-row export.

### Gap-driven shadow refinement

Implemented:

- first-wave gap observation;
- bounded follow-up query suggestions;
- explicit gap/reason codes;
- exact-query deduplication against executed queries;
- no provider call from shadow planning;
- no active routing change;
- API exposure of detected gaps and suggestions.

Current gap vocabulary includes:

- `sparse_yield`;
- `duplicate_or_excluded_pressure`;
- `no_returned_candidates`;
- `region_confirmation_missing`;
- `industry_confirmation_missing`;
- `discovery_novelty_unmeasured`.

### Administrative quality policy

PR #657 established the user/admin separation and persistent control-plane policy.

Verified chain:

- PR governance passed;
- Baseline CI passed;
- merged as `dc6c3ade812b52d3d99dcb6c2217fe2bd81f90f2`;
- post-merge Baseline CI passed;
- exact-SHA Deploy Stage passed;
- Stage Admin Workspace Acceptance #314 passed.

### Promotion-readiness policy integration

PR #658 connected persisted admin policy to offline promotion readiness.

The readiness path now:

1. reads the runtime policy in SQLite read-only/query-only mode;
2. recovers retained source/later quality metrics;
3. derives the canonical quality guard;
4. checks explicit hard-cap compliance separately;
5. remains fail-closed on missing policy/evidence/compliance;
6. does not activate steering.

Initial CI exposed an interface mismatch (`QualityGuard` was incorrectly treated as a wrapper). The failure was narrow: 1140 tests passed and 2 new tests failed. The one-line interface correction was followed by a successful full Baseline CI.

Final chain:

- Governance passed;
- full Baseline CI passed;
- merged as `dd19ba78f497223d62c3fe7574bfe508dcba1d37`;
- post-merge Baseline CI passed;
- exact-SHA Deploy Stage #1580 passed.

## Accepted technical decisions

1. Do not expose search quality coefficients to ordinary users.
2. Human search intent is a product contract; regime identifiers are stable machine contracts.
3. Admin quality policy and runtime resource caps are separate control dimensions.
4. Changing configuration does not authorize a new execution capability.
5. New adaptive intelligence begins shadow-only.
6. SearchGateway remains execution authority until separately governed promotion.
7. Multi-wave research must be bounded and gap-driven.
8. Follow-up queries should be tied to named evidence gaps.
9. Discovery success requires explicit novelty/rare-hit evidence; generic yield is insufficient.
10. Avoid invented universal weights before regime-specific evidence exists.
11. Retained traces/replay evidence should be used before paid/live evidence collection.
12. Runtime audit/readiness tools should be physically read-only where possible.
13. Exact deployed SHA is part of acceptance evidence.
14. Unknown critical evidence is represented explicitly and keeps the gate fail-closed.

## Current promotion boundary

The implementation is **not** authorized for active adaptive second-wave steering yet.

Required before promotion:

- sufficient heterogeneous scorable evidence;
- adequate per-action-family decided samples;
- acceptable supported/contradicted ratios;
- no high-confidence calibration regression;
- completed quality guard from persisted admin policy;
- explicit resource hard-cap compliance;
- no evidence of shadow routing changes;
- separate activation decision;
- explicit owner authorization for any live evaluation that may incur paid provider cost.

## Next critical implementation path

1. continue gap-specific hindsight scoring and retained-evidence aggregation;
2. inventory existing traces for zero-cost causal/historical matches to suggested follow-up queries;
3. build gap/regime calibration evidence;
4. close instrumentation gaps such as qualified-pool region/industry aggregates;
5. only after zero-cost evidence is exhausted, request owner authorization for bounded live/paid evaluation;
6. consider bounded active second wave only after the promotion gate is satisfied.

This document should be updated when the system moves from shadow refinement to any actively executed adaptive second-wave behavior.