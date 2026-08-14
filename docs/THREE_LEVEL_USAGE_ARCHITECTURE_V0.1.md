# Arrow Usage Architecture v0.2

**Date:** 2026-08-15  
**Parent:** #660 / #669  
**Architecture reference:** `Dimar4713/aimeton-architecture` ADR-019

## Product principle

Hunter SHALL NOT develop Preset, Guided and Professional as three parallel product streams.

Canonical dependency:

```text
Professional Core / Constructor
        ↓ package + constrain + explain
Guided Specialist Mode
        ↓ standardize + validate + freeze defaults
One-click Mass Presets
```

The professional layer is the semantic/capability superset. Guided and Preset are projections of that same lower-layer model.

## Foundation — Professional Core

Professional Core owns the canonical product semantics:
- versioned configuration schema;
- research stages/capabilities;
- source/provider roles within policy;
- evidence targets and sufficiency;
- stop/continue/refine/checkpoint logic;
- output contract/schema;
- research depth;
- human gates;
- resource/cost envelope;
- reusable versioned recipes;
- deterministic validation/resolution to configuration snapshot;
- one SearchGateway/policy execution boundary.

This layer is implemented first. It is not merely an advanced screen; it is the source of truth for what Hunter can do.

## Packaging — Guided Specialist Mode

Guided mode exposes a safe, understandable subset of Professional Core:
- start from a recipe/profile or simple Mission Brief;
- AI consultant clarifies content/form/depth;
- tune geography, industry, include/exclude;
- choose Auto / Крупная рыба / Баланс / Золотой песок;
- tune result size/form and research depth;
- review intermediate findings;
- narrow, broaden or deepen the mission;
- preserve Mission Brief/configuration revisions and dialogue provenance;
- preview material scope/cost expansion before execution.

Every Guided control MUST map to canonical Professional Core configuration semantics.

## Standard packaging — One-click Presets

Preset is built only from a proven lower-layer configuration:
- ready business service;
- minimum required inputs;
- expected output contract;
- known limits/cost envelope;
- one primary launch action;
- exact preset/lower-layer recipe version;
- canonical resolved configuration snapshot;
- saved evidence-backed result.

Examples for later validation:
- strongest target companies in a region;
- competitor map;
- supplier discovery;
- refresh saved list and show changes.

A preset is a validated versioned projection of the lower layer, never custom search code.

## Normative implementation order

```text
Professional Core contract
 -> expert scenario works
 -> Guided projection
 -> specialist UX/quality validation
 -> Preset standardization
 -> mass-use validation
```

Implementation issues follow this order:
- #672 — Professional Core / Constructor foundation;
- #671 — Guided Specialist Packaging, blocked on #672 contracts;
- #670 — One-click Presets, blocked on validated lower layers.

## Canonical state

All layers share exactly the same object graph:
- Workspace / Project;
- Mission + Mission Brief revisions;
- canonical configuration schema/version;
- resolved configuration snapshot;
- consultation history;
- Search/Analysis Run;
- Candidate + Evidence;
- decisions / notes / overrides;
- shortlists / saved result sets;
- cost / usage;
- admin policy provenance;
- audit trail.

## Progressive disclosure

User navigation is visually top-down:

`One-click -> Настроить -> Guided -> Профессиональный режим -> Constructor`.

But product construction is bottom-up:

`Constructor -> Guided packaging -> Preset`.

This distinction is critical: UI reveals complexity downward while engineering packages capability upward.

## Anti-divergence requirements

Acceptance SHALL prove:
1. equivalent Preset, Guided and Professional inputs resolve to equivalent canonical configuration snapshots;
2. all levels execute via the same SearchGateway/policy path;
3. entering a deeper mode reveals the same mission rather than cloning it;
4. returning to a simpler view preserves advanced state/provenance;
5. no Preset/Guided capability exists outside the Professional Core contract;
6. security, tenancy, budget, entitlements and admin policies are enforced below all views;
7. every run stores exact Mission Brief + configuration provenance.

## Persistence implications

Plan/implement:
- `configuration_schema_version`;
- `configuration_snapshot`;
- `professional_recipe` / `recipe_version`;
- `guided_profile` / `guided_profile_version`;
- `service_preset` / `service_preset_version`;
- explicit mapping/projection relations between layers;
- `preset_acceptance_evidence`;
- `preset_entitlement_binding`.

## Product-capital flywheel

```text
professional recipe
 -> repeated expert success
 -> guided packaging
 -> specialist validation
 -> normalized defaults
 -> accepted one-click preset
 -> mass-use evidence
 -> improve professional core
```

This is the key anti-fragmentation mechanism: expert know-how becomes mass-market simplicity through packaging, not through rewriting the service.

## Commercial implication

The architecture supports different customer sophistication levels while protecting one product core. Tariffs may expose different layers/resources, but entitlement MUST NOT fork business logic or state.

The shortest route to a sellable preset therefore begins with a sufficiently expressive and proven Professional Core, then deliberately compresses it into Guided and finally into One-click form.