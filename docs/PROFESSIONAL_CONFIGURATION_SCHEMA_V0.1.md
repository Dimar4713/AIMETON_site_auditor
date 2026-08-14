# Professional Configuration Schema v0.1

**Status:** working canonical contract  
**Parent:** #674 / #672 / #669  
**Machine-readable schema:** `config/professional_configuration.schema.json`

## Purpose

This contract is the semantic trunk of the Hunter Arrow architecture.

```text
Professional Core configuration
        ↓ constrained projection
Guided Specialist controls
        ↓ accepted standardization
One-click Preset
```

Guided and Preset layers are not allowed to invent execution semantics outside this contract.

## Canonical snapshot rule

Every Search/Analysis Run must retain an immutable resolved configuration snapshot containing the exact Mission Brief revision, effective search strategy, stages, evidence requirements, refinement semantics, interaction checkpoints, output contract, resource envelope and policy-version references used for execution.

Historical snapshots remain evidence even when the mission, admin policy or schema evolves later.

## Requested vs effective

The schema deliberately separates user-facing request from effective execution where policy/routing may resolve the value.

Example:
- `strategy.requested_intent = auto`
- `strategy.effective_regime = precision`

The same pattern should be extended as provider, depth, refinement and resource resolution become more explicit. A requested value never proves authorization or execution.

## Sections

### Mission binding
Binds the snapshot to one durable mission and exact Mission Brief revision.

### Target
Canonical geography, industry/category, entity types and include/exclude constraints.

### Strategy
User intent/effective regime and research depth.

### Stages
Ordered/composable professional capabilities. Each stage may define dependencies, provider roles and stage parameters, but provider secrets are prohibited.

### Evidence policy
Defines evidence targets, minimum direct-source expectations, provenance requirements and optional sufficiency rule.

### Refinement policy
Defines whether adaptive refinement is off, shadow-only or bounded-active; maximum additional waves; and allowed actions (`continue`, `refine`, `stop`). Authorization is still checked separately.

### Interaction policy
Defines AI-consultation participation, human checkpoints and whether material scope expansion requires preview before execution.

### Output contract
Defines the required presentation/business result independently from the search engine internals.

### Resource envelope
Defines hard requested ceilings for cost, duration and provider-call count. Effective enforcement remains below the presentation layer and subject to stricter admin/entitlement policy.

### Policy references
Pins the admin-search, quality and entitlement policy versions used when the snapshot was resolved.

### Provenance
Records who/what produced the configuration and from which Arrow layer (`professional`, `guided`, `preset`).

## Arrow projection rules

### Professional -> Guided
Guided UI exposes a bounded subset and human-readable abstractions, then compiles them into this schema. Every control must have a deterministic mapping.

### Guided/Professional -> Preset
A Preset stores a versioned parameterization/reference to an accepted lower-layer configuration. Launching a Preset resolves into the same schema before execution.

### Anti-divergence acceptance
For an equivalent business request:
1. create a Professional configuration;
2. express the same request through Guided controls;
3. express it through a Preset where available;
4. normalize each result;
5. compare canonical snapshots after removing provenance-only layer identifiers;
6. execution-significant fields must be equivalent.

## Compatibility with existing Hunter capabilities

The v0.1 contract is designed to absorb existing implementation rather than replace it:
- `auto / precision / balanced / discovery` search intents;
- admin search strategy/quality policy;
- provider/search policy;
- gap-driven shadow refinement and future bounded-active refinement;
- content/form/depth conversational mission changes;
- provider-cost observability;
- exact-SHA/provenance evidence;
- saved mission/run state planned by PRODUCT-01.

## Evolution rules

1. `schema_version` is mandatory.
2. Execution-significant unknown fields must not be silently ignored.
3. Breaking semantic changes require a new schema version and migration/compatibility policy.
4. Historical snapshots are not rewritten when defaults change.
5. Presets and recipes pin their version and resolve to a snapshot at run time.
6. Configuration contains no secrets.
7. Configuration never grants authorization; it is validated against current applicable governance before execution.

## v0.1 example

```json
{
  "schema_version": "0.1",
  "recipe_ref": {"recipe_id": "regional-target-hunt", "recipe_version": "1"},
  "mission_binding": {"mission_id": "mission-123", "mission_brief_revision": "3"},
  "target": {
    "geographies": ["Красноярск"],
    "industries": ["Стоматология"],
    "entity_types": ["company"],
    "include": [],
    "exclude": []
  },
  "strategy": {
    "requested_intent": "auto",
    "effective_regime": "precision",
    "research_depth": "working"
  },
  "stages": [
    {
      "id": "discovery",
      "capability": "company_discovery",
      "enabled": true,
      "depends_on": [],
      "provider_roles": ["regional_search", "open_web_search"],
      "parameters": {}
    }
  ],
  "evidence_policy": {
    "targets": ["region", "industry", "direct_or_official"],
    "minimum_direct_sources": 1,
    "require_provenance": true,
    "sufficiency_rule": null
  },
  "refinement_policy": {
    "mode": "shadow",
    "max_additional_waves": 1,
    "allowed_actions": ["continue", "refine", "stop"]
  },
  "interaction_policy": {
    "consultation_enabled": true,
    "checkpoints": ["before_material_scope_expansion", "after_intermediate_result"],
    "material_scope_change_requires_preview": true
  },
  "output_contract": {
    "format": "shortlist",
    "max_results": 50,
    "sections": ["company", "reason", "evidence"],
    "sort_by": "quality",
    "group_by": null
  },
  "resource_envelope": {
    "max_cost_rub": 1.0,
    "max_duration_seconds": 300,
    "max_provider_calls": 100
  },
  "policy_refs": {
    "admin_search_policy_version": "stage-current",
    "quality_policy_version": "stage-current",
    "entitlement_version": "product-dev"
  },
  "provenance": {
    "created_by": "user-or-system",
    "created_at": "2026-08-15T00:00:00Z",
    "source_layer": "professional",
    "source_preset_version": null,
    "source_guided_profile_version": null
  }
}
```

## Next implementation step

Add deterministic normalization/validation and round-trip tests, then bind the first representative Professional recipe to existing Hunter execution without changing provider routing. Only after that should #671 Guided controls be implemented.