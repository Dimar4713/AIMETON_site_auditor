# Search Observer evidence v2 replay contract

Status: supplemental contract for `docs/search-observer-evidence-collection-plan.md`.

This document does not authorize active steering, premium escalation, or paid provider usage.

## Historical baseline

The retained historical corpus remains valid schema-v1 evidence. Offline replay reproduces the canonical `N=30` signature:

- 30 comparable outcomes;
- 18 aligned;
- 12 disagreements: 9 over-refine, 2 under-refine, 1 continue-without-gain;
- 29/30 later waves produced quality gain.

Historical schema-v1 artifacts do not retain the exact per-direction bounded telemetry presented to the Observer. Observer-input cohort fields are therefore intentionally unavailable for that corpus.

## Contract for future justified live evidence

Every future live-validation artifact must:

1. emit `schema_version=2` or later;
2. retain the bounded `SearchWaveTelemetry` actually presented to the shadow Observer;
3. preserve per-direction duplicate-domain ratio, unique-domain count, provider-result counts, attempt states and other bounded telemetry fields;
4. retain `routing_changed=false` for Observer-input evidence;
5. be eligible for offline replay without provider or LLM calls;
6. produce a replay bundle containing SHA-256, byte size, schema version and scenario count for each input evidence file;
7. embed calibration diagnostics in the replay bundle;
8. preserve `routing_changed=false`, `steering_enabled=false`, and `promotion_eligible=false` for the replay artifact.

## Spend and activation guard

The v2 format is an instrumentation requirement, not a reason to purchase or launch a new live batch. The global sample floor is already satisfied at `N=30`.

A new paid batch requires a concrete unresolved quality hypothesis plus explicit spend authorization. Active steering remains disabled until separate promotion and activation decisions are satisfied.
