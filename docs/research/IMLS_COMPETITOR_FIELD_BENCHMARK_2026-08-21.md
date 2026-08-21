# IMLS / services-realty.ru competitor field benchmark

**Date:** 2026-08-21  
**Status:** ACCEPTED_PROJECT_INPUT  
**Target:** `https://services-realty.ru/checksubject` → `https://77.services-realty.ru/checksubject`  
**Competitor entity:** ООО «ИМЛС»  
**Field test:** current deployed AIMETON `/api/analyze`, stage SHA `643f493dd7410c4786c3f207bfb43b24d659768e`

## Why this benchmark matters

The live field test proved that AIMETON Site Auditor already goes beyond static website analysis. From one competitor URL it reconstructed a candidate legal entity, products, external context, economic signals, a commercial opportunity and an action package.

At the same time, the same run correctly reported:

- `sufficiency_level = L0`;
- `identity_state = unresolved`;
- `profile_completeness = 0.60`;
- `evidence_quality = 0.0`;
- `client_release_eligible = false`;
- `legal_events = not_searched`;
- discovery hints were not promoted to evidence without primary-document verification.

This is the key project lesson: **reasoning capability is now ahead of evidence acquisition and verification capability.** The next product step is not “more fluent LLM text”; it is a stronger primary-source, temporal and entity-intelligence substrate.

## What the competitor does well and AIMETON should borrow

Borrow the product and operational ideas, not the legacy implementation.

### 1. Action-oriented entry point

IMLS packages complex data collection behind simple user intents such as checking a person, company or property.

AIMETON should expose similarly direct user jobs:

- Check company;
- Check person / founder / executive;
- Check sole proprietor;
- Check site/domain;
- later: property, supplier, employer, investment target, project.

The internal OSINT/provider complexity must stay behind the product boundary.

### 2. Broad source coverage

IMLS publicly positions its checks around multiple official/open sources, including tax, enforcement, courts, bankruptcy and real-estate-related data.

AIMETON should reach parity first through a provider family:

- FNS / EGRUL / EGRIP;
- FNS accounting reporting (GIR BO);
- FSSP;
- KAD / arbitration;
- Fedresurs / bankruptcy;
- later: procurement, RNP, licences, patents, accreditation, Rosreestr/property packs where legally and technically appropriate.

### 3. Monitoring instead of one-off reports

IMLS turns checks into recurring monitoring. AIMETON should make “watch for changes” a first-class action after every entity report.

Required model:

```text
Observation -> Snapshot -> Diff -> Event -> Signal -> Alert
```

### 4. Historical archive as moat

The competitor has accumulated historical listing data. AIMETON cannot instantly recreate years of history, so all future observations must be stored as time-addressable evidence rather than overwritten.

Principle:

> Every observation that may become economically meaningful later should be preserved with source, time, entity and digest metadata.

### 5. Vertical packaging

IMLS gains value by embedding checks into a specific money-moving workflow (real estate). AIMETON should use a shared intelligence kernel with vertical product packs rather than create isolated products with separate data logic.

Candidate packs:

- AIMETON Counterparty;
- AIMETON Employer Check;
- AIMETON Supplier Intelligence;
- AIMETON Property Intelligence;
- AIMETON Investment Due Diligence;
- AIMETON Competitive Intelligence.

## What AIMETON must not copy

Do not copy an aggregator architecture where source fields are simply assembled into a static card.

Do not bind domain logic directly to one registry/provider.

Do not treat search snippets as verified facts.

Do not overwrite historical state.

Do not make PERSON / COMPANY / PROPERTY separate intelligence silos.

Do not use opaque or ambiguous subscription mechanics; monitoring must have transparent opt-in, cadence, price and cancellation semantics.

## AIMETON target architecture

```text
DISCOVER ENTITY
  -> RESOLVE IDENTITY
  -> OFFICIAL REGISTRY FABRIC
  -> WEB / COMMERCIAL FABRIC
  -> DOCUMENT FETCH + EXACT EVIDENCE
  -> CLAIM & EVIDENCE LEDGER
  -> TEMPORAL MEMORY
  -> ENTITY / RELATIONSHIP GRAPH
  -> EVENT DETECTION
  -> ECONOMIC SIGNALS
  -> AUTONOMOUS INVESTIGATION
  -> EXPLAINED DECISION
  -> CONTINUOUS WATCH
```

Generic entity types should converge on one graph model:

- PERSON
- COMPANY
- SOLE_PROPRIETOR
- DOMAIN
- WEBSITE
- PROPERTY
- PRODUCT
- ADDRESS
- DOCUMENT
- EVENT

## Field-test gaps converted into required improvements

### P0 — Primary-source company identity provider pack

Once a candidate INN/OGRN is discovered, the system must automatically fetch and verify primary identity evidence.

Minimum output:

- legal name;
- INN;
- OGRN;
- status;
- registration date;
- legal address;
- OKVED;
- executives;
- founders where available;
- source document URL / timestamp / digest / locator.

Expected benchmark movement for IMLS:

```text
identity_state: unresolved -> resolved
```

### P0 — GIR BO verified financials

Replace search-snippet financial hypotheses with primary financial evidence and time series.

Required derived features:

- revenue trend;
- profit trend;
- assets/liabilities;
- receivables/payables where available;
- growth quality;
- anomalies and one-off-change warnings.

Expected benchmark movement:

```text
financials: weak/discovery -> verified
```

### P0 — FSSP / KAD / Fedresurs legal-event pack

Required capabilities:

- enforcement proceedings and amount/time dynamics;
- arbitration roles, amounts and recurring counterparties;
- bankruptcy/distress event states;
- exact source provenance;
- temporal event normalization.

Expected benchmark movement:

```text
legal_events: not_searched -> verified/partially_verified
```

### P0 — Evidence promotion pipeline

Search results remain `discovery_hint` until the primary document is fetched and its relevant claim is extracted.

Required transition:

```text
search hint
-> source candidate
-> fetched document
-> exact quote/locator/digest
-> normalized claim
-> entity-bound evidence
-> accepted/rejected/conflicting state
```

No narrative field should raise evidence quality merely because an LLM can synthesize it.

### P0 — Temporal Evidence Memory

Persist observations and accepted evidence with observed-at and valid-time semantics where possible.

Minimum objects:

- observation;
- snapshot;
- diff;
- event;
- signal.

Do not overwrite previous values.

### P1 — Relationship / Entity Graph

Use discovered identifiers and shared attributes to build typed relations:

```text
Company
  -> executives
  -> founders
  -> affiliates
  -> domains/sites
  -> addresses
  -> phones/emails
  -> property/assets where lawful
  -> court cases
  -> procurement
  -> vacancies
  -> products/listings
  -> counterparties
  -> events over time
```

Each edge needs provenance and confidence.

### P1 — Cross-source economic signals

Create derived signals from combinations of verified observations rather than individual fields.

Examples:

- enforcement acceleration;
- litigation inversion (historically plaintiff, suddenly defendant);
- supplier-conflict concentration;
- hiring contraction / expansion;
- government-customer dependence;
- management instability;
- revenue-growth quality;
- digital decline / expansion.

### P1 — Autonomous investigation loop

A signal should create follow-up questions automatically.

Example:

```text
new enforcement spike
-> inspect arbitration
-> identify creditors
-> inspect financial trend
-> inspect procurement/customer loss
-> inspect workforce/news
-> produce competing hypotheses
-> test them against evidence
```

The result must distinguish fact, signal, hypothesis and conclusion.

### P1 — One-click Company Check UX

Provide a compact initial product surface:

```text
What to check?
[Company] [Person] [Sole proprietor] [Site]
```

The user should not need to understand providers, crawlers or mission internals.

### P1 — Continuous watch UX

Every eligible report should offer:

`Watch for changes`

with explicit monitored signals, cadence, notification channel, price/budget and stop conditions.

### P2 — Property Intelligence

Add as a provider/vertical pack over the same Entity Graph and Evidence Ledger rather than a separate subsystem.

### P2 — Additional economic-source families

Evaluate and prioritize:

- government procurement / contracts / RNP;
- licences;
- patents and trademarks;
- accreditation/certification;
- maps/reviews;
- job boards/career pages;
- marketplaces/listings/prices;
- company news and public channels;
- DNS/RDAP/TLS/subdomain and other digital-footprint evidence.

## Regression benchmark: COMPETITOR-RU-01

The IMLS target becomes a durable field benchmark.

**ID:** `COMPETITOR-RU-01`  
**Entity:** ООО «ИМЛС»  
**Seed URL:** `https://services-realty.ru/checksubject`

Track at least:

- HTTP success;
- entity resolved state;
- profile completeness;
- evidence quality;
- sufficiency level;
- count of primary documents;
- count of accepted claims;
- verified identity vertical;
- verified financial vertical;
- verified legal-events vertical;
- temporal events found;
- economic signals with primary evidence;
- unsupported-claim count;
- client release eligibility.

Target progression:

```text
L0 -> L1 -> L2 -> L3 -> L4
identity unresolved -> resolved
evidence_quality 0.0 -> materially > 0
legal_events not_searched -> verified/partially_verified
```

The benchmark must not be gamed with target-specific hard-coded facts. It is a real external regression target used to measure general provider/evidence capability.

## Product differentiation to preserve

Competitor pattern:

> aggregate data and show a check result.

AIMETON target:

> investigate an entity, prove the important claims, detect changes, explain economic meaning, test hypotheses and continue watching.

Short form:

**Data -> Evidence -> Relations -> Time -> Signals -> Investigation -> Decision.**

## Implementation ordering

1. FNS identity provider + evidence promotion.
2. GIR BO financial provider.
3. FSSP + KAD + Fedresurs event providers.
4. Temporal Evidence Memory.
5. COMPETITOR-RU-01 automated regression scoring.
6. Entity/Relationship Graph.
7. Cross-source signal engine.
8. Continuous watch.
9. Autonomous investigation planner.
10. Additional vertical packs.

## Acceptance principle

AIMETON should copy competitor **coverage, user simplicity, monitoring discipline and historical accumulation**, while surpassing it through **primary evidence, provenance, temporal reasoning, entity relationships, conflict handling and autonomous hypothesis testing**.
