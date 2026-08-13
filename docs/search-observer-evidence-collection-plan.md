# Search Observer heterogeneous evidence collection plan

Status: shadow-only evidence program. This document does not authorize active steering or paid provider usage.

## Objective

Collect enough direction-scoped causal outcomes to evaluate the promotion gate merged in PR #588 without changing routing or provider policy.

## Current baseline

- scored outcomes: 2
- heterogeneous batches: 1
- current state: `shadow_only`
- target floor: 30 scorable outcomes
- per action-family floor: 5 decided outcomes for any family considered for promotion

## Quality-first live finding — 2026-08-13

Exact-SHA live validation run `31656295200` on `8a677339b78f902b07686beb83880849c3174a76` confirmed that a second search wave can materially increase useful yield while also increasing duplicate/excluded waste.

Observed examples:

- metalworking / official-site direction: qualified/direct candidates increased from 3/3 to 12/12 after one additional same-direction query; the `continue` recommendation was scored as supported;
- metalworking / directory direction: qualified/direct candidates increased from 1/1 to 8/8, but duplicate/excluded waste also grew materially; the `refine` recommendation was contradicted by the later-wave evidence;
- dentistry / Krasnoyarsk: the Observer hit the 20-second wall-clock guard and produced no scorable recommendation.

During the current quality-first phase, latency and cost growth alone do not outweigh a demonstrated search-quality improvement, but existing hard caps, provider policy, routing authority restrictions and premium-escalation restrictions remain unchanged.

The Observer timeout is therefore treated as a quality-evidence completeness defect. The default wall-clock allowance is raised from 20 to 30 seconds while remaining bounded and shadow-only. The HTTP client timeout must stay above the Observer wall-clock guard so the outer Observer timeout remains the authoritative classified outcome.

## Batch design

Use multiple industries, regions and query shapes. Prefer batches that differ along at least two dimensions from the previous accepted batch.

Suggested matrix:

1. healthcare / regional services / local official-site discovery
2. industrial manufacturing / B2B suppliers / company discovery
3. professional services / accounting or legal / organization discovery
4. equipment and machinery / product-category company discovery
5. construction / contractors / regional company discovery
6. IT and software services / vendor discovery
7. logistics / carriers and warehouses / regional discovery
8. education / training providers / organization discovery

Each batch must preserve:

- exact deployed SHA;
- Observer shadow-only mode;
- same-direction second-wave continuation for causal scoring;
- `routing_changed=false`;
- provider concurrency/cooldown/circuit/quota policy unchanged;
- no premium escalation;
- explicit spend authorization before any paid live batch;
- machine-readable evidence artifact with cost and verdicts.

## AIMETON Search Benchmark v1 — approved experiment program

Purpose: replace subjective comparisons with reproducible measurements and position AIMETON, Perplexity and combined AIMETON+Perplexity execution on the same task set.

Initial target: 30 benchmark tasks, balanced across ten experiment groups.

| Group | Task family | Primary measurements |
|---|---|---|
| A | Known company intelligence | official-source recall, factual correctness, provenance completeness |
| B | Regional company hunt | unique qualified companies, direct/official yield, precision |
| C | Narrow B2B niche | recall, precision, qualified-per-query |
| D | Low-information regional company | source discovery depth, primary-source recovery |
| E | Contradictory company facts | contradiction detection, conflict resolution, evidence quality |
| F | Deep market/supply-chain research | breadth, depth, useful-evidence density |
| G | Russian regulatory/standards sources | domain-source recall, official-source share, citation correctness |
| H | Search economics | RUB per qualified candidate, RUB per verified fact, provider-call count |
| I | Time efficiency | useful evidence per second, latency to first verified fact, total mission latency |
| J | Decision usefulness | actionability, evidence completeness, unsupported-claim rate |

### Benchmark contenders

Every benchmark task should be executable, where technically and legally available, in three comparable modes:

1. `AIMETON_NATIVE` — AIMETON Search Gateway / Search Observer only;
2. `PERPLEXITY` — Perplexity search/research capability as an external contender;
3. `AIMETON_PLUS_PERPLEXITY` — Perplexity used as one bounded external search organ inside AIMETON, with AIMETON retaining orchestration, evidence normalization and decision governance.

### Canonical metrics

At minimum retain per task and contender:

- task_id, category, region, industry, timestamp and exact system/version identifiers;
- unique sources and unique domains;
- official/direct source count and share;
- qualified candidate count;
- verified facts and contradicted facts;
- unsupported claims;
- duplicate and excluded result counts;
- useful-evidence density;
- citation/provenance completeness;
- time to first verified fact and total latency;
- provider/search call count;
- measured cost where available;
- final actionability score under the same rubric;
- raw evidence artifact sufficient for independent re-scoring.

### Fairness and reproducibility rules

- identical task wording and task-specific constraints across contenders;
- preserve raw outputs and source lists before human interpretation;
- blind or deterministic scoring where practical;
- separate retrieval quality from answer-writing quality;
- no promotion decision from a single task or single domain;
- report confidence intervals or at least sample counts with every aggregate;
- document unavailable/unsupported metrics instead of substituting estimates;
- Perplexity comparison does not authorize paid usage beyond explicit owner approval and configured hard caps.

### Experiment sequence

1. Freeze v1 task corpus and scoring rubric.
2. Implement machine-readable benchmark schema and artifact layout.
3. Run a small dry batch with no more than three tasks to validate scoring and evidence capture.
4. Run the full 30-task benchmark only after instrumentation is validated.
5. Compare `AIMETON_NATIVE`, `PERPLEXITY`, and `AIMETON_PLUS_PERPLEXITY` by task group and overall, not only by one aggregate score.
6. Feed findings back into Search Observer policy, provider routing and source-role priorities while preserving shadow-first governance.

This benchmark is an evidence program, not an authorization to activate autonomous routing or purchase premium provider capacity.

## Evidence ledger fields

For every scored outcome retain:

- batch/scenario identity;
- mission_id and attempt_id;
- direction_index;
- Observer action and confidence;
- source query;
- source and later snapshots;
- marginal qualified/direct-or-official/unique/raw yield;
- duplicates and exclusions;
- latency and search cost;
- deterministic verdict and score;
- routing_changed flag;
- deployed SHA and workflow run.

## Promotion review cadence

Recompute the gate after each heterogeneous batch, but do not interpret early ratios as promotion evidence before the global and per-family minimum sample floors are met.

If an action family lacks enough decided outcomes, it remains shadow-only independently of other families.

`escalate` is excluded from automatic steering and remains under a separate economic/policy authorization gate.
