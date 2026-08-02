# SA-SR-G3 — executable resilient AI/LLM plan

Part of #87.

## Goal

Deliver a deterministic, fail-closed AI contour before enabling real paid or production LLM calls. AI output must never erase accepted evidence, silently repair itself without trace, create unsupported sources, or bypass Policy Guard and Report Gate.

## Delivery slices

### AI-1 — bounded schema validation and retry

- introduce a schema-bound AI step result with explicit attempt metadata;
- validate every structured response before facts enter Ledger/Evidence;
- permit at most one bounded repair/retry in the first slice;
- classify exhaustion as typed `schema_validation_failed` / `ai_failure`;
- preserve all documents and evidence accepted before the failed AI step;
- force `blocked` or `degraded` outcome and deny client release;
- add deterministic tests with no external model invocation.

Acceptance evidence:

- invalid response followed by valid repair succeeds within the bound;
- repeated invalid responses stop at the bound;
- attempts and reason codes are persisted without prompt, credential or secret disclosure;
- prior evidence digest remains unchanged;
- Report Gate remains fail-closed.

### AI-2 — provenance-safe facts

- require `model`, prompt/schema version, input digest, confidence and provenance/status;
- prohibit heuristic or fallback output from becoming `verified`;
- preserve conflicting facts rather than resolving them silently;
- prove identical evidence snapshots produce a stable facts structure.

### AI-3 — source-preserving synthesis

- synthesize only from the accepted Ledger/Evidence snapshot;
- reject links, claims and entities absent from the input snapshot;
- record typed unsupported-claim and unsupported-source reasons;
- keep fallback output `preliminary_hypothesis` and not client-eligible.

### AI-4 — Policy Guard boundary

- represent AI-proposed next actions as candidates only;
- require Policy Guard approval before execution;
- reject disallowed actions with a typed reason;
- prove prompt-injected instructions cannot bypass policy, budget or provider gates.

### AI-5 — accounting and negative matrix

- account attempted, accepted and billed attempts separately;
- enforce retry and cost bounds without calling paid providers in CI;
- cover negative schema, prompt injection, hallucinated claim/source, timeout and provider/AI failure;
- expose only sanitized operational evidence.

## Invariants

- no real provider/LLM calls in deterministic CI slices;
- no new cost or budget change;
- no secret, prompt, token, credential or raw model payload publication;
- no destruction or replacement of already accepted documents/evidence;
- no client release after typed AI failure or unresolved validation error;
- no AI action execution without Policy Guard;
- no OCC-49, architecture invariant, legal obligation or production-state change.

## Required order

1. Merge this executable plan only on full required CI green.
2. Open AI-1 red-first delivery PR.
3. Implement only the contract gaps proven by AI-1 regressions.
4. Merge only on full green, then advance sequentially through AI-2…AI-5.
5. Reconcile #87 acceptance and Evidence of Done after every merged slice.
