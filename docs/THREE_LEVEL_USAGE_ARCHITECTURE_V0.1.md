# Three-Level Usage Architecture v0.1

**Date:** 2026-08-15  
**Parent:** #660  
**Architecture reference:** `Dimar4713/aimeton-architecture` ADR-019

## Product principle

Hunter SHALL expose three levels of use over one canonical mission/capability/evidence model.

### Level 1 — Preset / One-click
For a mass user who wants a business result with minimal configuration.

- choose a ready service;
- provide minimal context;
- see expected output, limits and cost envelope;
- press one main action;
- receive a saved, evidence-backed result.

Examples:
- find the strongest target companies in a region;
- map competitors;
- find suppliers;
- refresh a saved list and show changes.

The preset is a versioned validated configuration, not a hardcoded UI shortcut.

### Level 2 — Guided / Tunable
For an advanced user who wants to influence the result without building the workflow.

- start from a preset or simple mission;
- refine goal with AI consultant;
- tune geography, industry, include/exclude criteria;
- choose Auto / Крупная рыба / Баланс / Золотой песок;
- select result form and research depth;
- inspect intermediate findings;
- narrow, broaden or deepen the mission;
- preserve Mission Brief revisions and dialogue provenance.

### Level 3 — Professional Constructor
For analyst/researcher/integrator/power user.

- compose research stages/capabilities;
- select source/provider roles within policy;
- define evidence targets;
- configure stop/refine/checkpoint logic;
- define output schema and review gates;
- set allowed resource/cost envelope within entitlement;
- save reusable professional recipes/templates;
- promote successful recipes into validated presets after acceptance.

Professional mode never bypasses security, tenancy, budget, provider or execution policies.

## Canonical architecture

```text
Preset UI ───────────┐
Guided UI ───────────┼─> canonical Mission Brief / capability configuration
Constructor UI ──────┘                │
                                      v
                             validation + policy
                                      │
                                      v
                              SearchGateway / tools
                                      │
                                      v
                             Evidence + Results
```

All levels use the same:
- Workspace/Project;
- Mission and Mission Brief revisions;
- run history;
- candidates and evidence;
- decisions/notes/shortlists;
- cost/usage;
- admin policy provenance;
- audit trail.

The levels differ only in how much configuration is visible/editable.

## UX rule — progressive disclosure

The user can move deeper without losing context:

`one-click service -> Настроить -> guided mode -> Профессиональный режим -> constructor`.

Returning to a simpler view does not discard advanced configuration; it presents an understandable summary and marks non-default choices.

## Preset lifecycle

`draft -> tested -> accepted -> published -> deprecated -> retired`.

A preset requires:
- customer job;
- input contract;
- output contract;
- validated configuration;
- quality evidence;
- cost/resource envelope;
- tariff mapping;
- telemetry;
- version and rollback/deprecation path.

## Expert-to-mass product flywheel

```text
professional recipe
 -> repeated successful use
 -> quality/economic evidence
 -> normalize/configure defaults
 -> acceptance
 -> publish as one-click preset
```

This is a core product-capital loop for AIMETON: expert know-how becomes a scalable service rather than remaining bespoke work.

## Persistence implications

Add/plan entities:
- `service_preset`;
- `service_preset_version`;
- `configuration_snapshot`;
- `professional_recipe` / reusable template;
- `recipe_version`;
- `preset_acceptance_evidence`;
- `preset_entitlement_binding`.

Every Search Run references the exact resolved configuration used, regardless of which UI level produced it.

## Acceptance requirements

### Preset
A novice can obtain a useful saved result without understanding search mechanics.

### Guided
A user can improve content/form/depth through bounded controls and dialogue without rebuilding the mission.

### Professional
A power user can build and reuse a custom research recipe, while validation and policy prevent unsafe/unauthorized execution.

### Cross-level
The same mission can be opened at another level without losing history, evidence, settings or provenance.

## Commercial implication

This naturally supports a product ladder:
- preset = lowest friction / fastest time-to-value;
- guided = more adaptation and value;
- professional = highest flexibility and organizational value.

Tariffs may gate advanced levels and resources, but must not fork the underlying product domain model.
