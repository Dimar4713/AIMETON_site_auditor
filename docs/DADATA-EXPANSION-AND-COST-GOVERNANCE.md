# DaData expansion and paid-provider cost governance

Status: approved planning baseline
Date: 2026-08-08

## Purpose

Expand DaData usage beyond minimal registry-mirror identity lookup while making every paid external provider economically observable and governable per customer, mission and subscription tier.

## DaData roadmap

### Phase 1 — identity mirror (current / immediate)
- Keep `findById/party` for INN/OGRN resolution.
- Surface legal name, INN, OGRN and registration status in owned analysis.
- Keep DaData explicitly non-authoritative: `authority_verified=false`; official FNS evidence remains a separate gate.
- Preserve typed states: verified / unresolved / conflicting / unavailable.

### Phase 2 — affiliation discovery
- Add affiliated-company discovery by founder/director identifiers where DaData supports it.
- Use affiliation results as discovery candidates, not as authoritative ownership proof.
- Feed candidate organizations back into the evidence pipeline and require primary-source verification before promotion to evidence.

### Phase 3 — address and entity normalization
- Add address normalization / FIAS-GAR resolution for legal, branch and contact addresses.
- Use normalized addresses to improve branch linking, duplicate detection and regional attribution.
- Record raw value, normalized value, provider, timestamp and confidence/provenance.

### Phase 4 — bank / requisites enrichment
- Add bank/requisite resolution where useful for company intelligence and verification.
- Keep banking data scoped to business-analysis use cases and avoid collecting unnecessary personal data.

### Phase 5 — APIs requiring Secret key
- Add methods that require `API key + Secret key` / `X-Secret` only when they materially improve the product, such as supported cleaning/standardization or brand/entity resolution.
- Never send `DADATA_SECRET` to endpoints that do not require it.
- Keep both credentials in GitHub Environment secrets and inject them only into the runtime that needs them.

## Mandatory cost telemetry for paid resources

Every paid external call MUST emit a metering record even when the provider is in debug/unlimited-quality mode.

Minimum record fields:
- `timestamp_utc`
- `provider`
- `operation` / endpoint class
- `mission_id`
- `customer_id` or tenant/account scope when available
- `subscription_tier`
- `request_id` / correlation id
- `units_requested`
- `units_consumed` when provider returns them
- `provider_cost_native`
- `provider_currency`
- `normalized_cost` and accounting currency when conversion is available
- `cache_hit`
- `success` / failure class
- `latency_ms`
- `result_count`
- `quality/evidence outcome` when measurable
- `budget_policy_decision` (allowed / degraded / denied / fallback)

Secrets, raw auth headers and provider credentials MUST NOT enter telemetry.

## Budget and tariff control model

The runtime must separate four concepts:
1. **Provider hard limits** — external account/provider quota and safety caps.
2. **AIMETON technical safety limits** — finite timeouts, loop guards, SSRF/rights controls.
3. **Customer budget envelope** — money/units allowed for a tenant, mission, day/month or contract period.
4. **Subscription quality policy** — which providers, depth, parallelism, refresh frequency and evidence targets are available for a subscription tier.

Customer-facing quality may be controlled by policy such as:
- number and class of paid providers;
- maximum external calls / cost per mission;
- depth of evidence crawl and enrichment;
- refresh frequency;
- fallback to premium sources;
- concurrency / latency target;
- retained history and reporting detail.

Do not implement quality reduction as silent data corruption. If a tier/budget prevents further enrichment, the report must expose a typed state such as `budget_limited` / `tier_limited` / `provider_quota_limited`.

## Accounting / FinOps requirements

- Maintain append-only usage ledger for chargeable provider events.
- Aggregate by provider, operation, customer, mission, subscription and billing period.
- Support reconciliation against provider invoices/usage dashboards.
- Support internal cost, customer billable usage and margin as separate values.
- Support budget alerts at configurable thresholds (for example 50/80/100%).
- Support policy actions: warn, degrade, require approval, deny paid fallback.
- Keep historical price-card versions so old usage can be priced reproducibly.

## Implementation sequence

1. Complete DaData report integration and Stage acceptance.
2. Introduce a common `ProviderUsageEvent` / usage-ledger contract in the Search Gateway / external-provider layer.
3. Instrument DaData first, then Yandex/Tavily/LLM and every other paid provider through the same contract.
4. Add per-mission and per-customer aggregation.
5. Add subscription/budget policy evaluation before paid calls.
6. Add post-call reconciliation using actual provider usage/cost where available.
7. Add operator dashboards and customer-visible usage/budget summaries.
8. Add tariff/versioned price-card layer only after raw metering is trustworthy.

## Acceptance principles

- A paid call without a traceable usage event is a defect.
- A usage event without customer/mission attribution, when attribution is available, is incomplete.
- Billing policy must not be embedded separately inside each provider adapter; adapters report usage, a shared policy layer decides access and budget behavior.
- Debug mode may relax economic ceilings for engineering, but MUST NOT disable metering.
- Provider costs and customer price are different quantities and must be stored separately.
