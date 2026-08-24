# ACCB Layer B no-paid dry-run — 2026-08-23

**Status:** implemented research dry-run / paid execution NOT authorized  
**Architecture tracker:** `Dimar4713/aimeton-architecture#132`  
**Execution evidence tracker:** `#798`  
**Frozen architecture preregistration:** `Dimar4713/aimeton-architecture@b47b937873ef980601b5c741af9b327fb18365bc`  
**Spend authorized by this implementation:** `0 RUB`

## Purpose

This dry-run turns the frozen ACCB Layer B diagnostic design into deterministic, testable execution scaffolding **without calling an LLM provider**. It closes the local implementation gap between the architecture preregistration and a future owner-approved paid calibration tranche.

It does not execute the 15 planned model calls, does not claim a universal ECC/AMCE threshold, and does not convert the completed five-model low-context calibration into a universal model ranking.

## Immutable architecture snapshot

The Site Auditor snapshot under:

`docs/research/accb_layer_b_snapshot/b47b937873ef980601b5c741af9b327fb18365bc/`

contains byte-identical copies of:

- `ACCB_PREREGISTRATION_v0.4_FROZEN.json` — Git blob `7585474f54bbb4f6e1e3d59085618ab639b1aa4d`;
- `ACCB-DEV-004.scenario.json` — Git blob `7ae1d4cc1819538a3acccc0d7700dc2ca7606161`.

`scripts/accb_layer_b_dry_run.py` recomputes Git blob hashes before doing any dry-run work and fails closed on snapshot drift.

## Deterministic context assembly v0.1

The assembler implements the frozen anchors `32K / 128K / 512K` as deterministic **logical whitespace-token targets**. The five temporally significant B1..B5 events are inserted at the frozen relative targets `0.08 / 0.28 / 0.54 / 0.72 / 0.94`; B6 remains the checkpoint/task. Filler ordering and distractor assignment are fully deterministic from the frozen hash-derived assembly seed.

The deterministic outputs are:

| Logical target | Assembly seed u32 | Context SHA-256 | Bytes | Filler distractor density |
|---:|---:|---|---:|---:|
| 32768 | 3297921442 | `ea934093e6ba7e27f57edc4e3bd6647232a458b967155f3e1ab26ac13cbe259d` | 470162 | 0.349995 |
| 131072 | 1227261303 | `e3f087711b00dbf1f8d261431cf05899bd5330de511bb1bd2fe5a5bda625ebbd` | 1880717 | 0.350003 |
| 524288 | 990456894 | `b37c2fe5907f80a4e52144c55fe8c3a3bcbbc0e7d81b9f633e41998511b9219e` | 7522522 | 0.350000 |

These hashes are regression-locked in `tests/test_accb_layer_b_dry_run.py`.

## Tokenization boundary

The logical whitespace-token count is **not** claimed to equal provider billing tokens. Different provider tokenizers may split the deterministic filler differently.

The public RouterAI provider-selection documentation exposes endpoint context limits, `max_prompt_tokens`, `max_completion_tokens`, `supported_parameters`, pricing and pricing tiers through the read-only endpoint census API. The public parameter documentation defines `seed`, but the reviewed public documentation does not establish a free provider-exact token-count endpoint that can replace provider usage evidence.

Sources:

- https://routerai.ru/docs/guides/overview/provider-selection
- https://routerai.ru/docs/guides/overview/parameters

Therefore the future paid path must either obtain provider-exact input counts through a separately preregistered no-generation tokenizer method, or use a preregistered adaptive method and record actual provider usage. The offline 32K/128K/512K logical targets must never be written into `L_model_input` as if they were measured provider tokens.

## Seed capability boundary

RouterAI documents `seed` as an optional integer and explicitly notes that determinism is not guaranteed for every model. The frozen ACCB policy therefore separates two controls:

1. **assembly seed** — mandatory, internal, deterministic, and already frozen;
2. **provider seed** — capability-dependent best effort only.

Retained runtime endpoint evidence advertises `seed` for GLM 5.2, Qwen3.7 Plus and Kimi K3 on the selected chat routes. Their generic chat wire key can be contract-tested locally without a provider request. The retained selected DeepSeek endpoint did not advertise `seed`, so the dry-run omits it. RouterAI advertised `seed` for GPT-5.6 Sol, but the validated Sol route is native Responses and earlier generic controls required provider-native translation; this implementation therefore keeps Sol provider seed omitted until that Responses wire contract is independently proven without guessing.

No provider seed result is interpreted as a universal determinism guarantee.

## Retained-pricing dry-run

The implementation independently recomputes the frozen conservative planning estimate from retained endpoint pricing evidence and the full `8192` output-token cap for every cell:

| Model | 32K | 128K | 512K | Model total, RUB |
|---|---:|---:|---:|---:|
| GLM 5.2 | 14.570763 | 39.049645 | 136.965172 | 190.585580 |
| DeepSeek V4 Pro 0813 | 11.423478 | 31.006584 | 109.339006 | 151.769068 |
| Qwen3.7 Plus | 2.260676 | 5.651690 | 57.647237 | 65.559603 |
| Kimi K3 | 27.419527 | 63.978896 | 210.216372 | 301.614794 |
| GPT-5.6 Sol | 15.895378 | 37.089215 | 239.313744 | 292.298337 |

Whole 15-cell planning estimate: **`1001.827382 RUB`**.

This is an implementation consistency check against retained pricing, not a live admission receipt and not a budget authorization. A fresh read-only endpoint census and a complete recomputation remain mandatory immediately before any paid execution.

## CI and safety contract

`Baseline CI` owns unit/regression execution in its isolated Python environment and includes `tests/test_accb_layer_b_dry_run.py`. `.github/workflows/accb-layer-b-dry-run.yml` is deliberately stdlib-only: it compiles the harness, materializes the exact deterministic report and validates the no-provider/no-spend invariants on the existing self-hosted Site Auditor runner. Neither workflow uses Marketplace Actions for this path, and the dedicated dry-run guard requires no RouterAI secret or provider SDK.

The generated dry-run report must assert:

- `network_calls_performed = 0` for the dry-run harness itself;
- `routerai_generation_calls_performed = 0`;
- `spend_authorized_rub = 0`;
- `planned_calls = 15`;
- `planning_cost_recomputed_rub = 1001.827382`;
- every context keeps `provider_token_count = null` until provider-exact tokenization is measured.

The existing paid ACCB trigger file `docs/research/ACCB_ROUTERAI_LIVE_TRIGGER_2026-08-22.json` is deliberately untouched, so merging this work cannot activate the historical paid push trigger.

## Remaining gates before paid Layer B

Paid execution remains fail-closed until all of the following are true:

1. provider/tokenizer input-count method is resolved and preregistered without laundering logical token targets into measured usage;
2. fresh read-only RouterAI endpoint census is captured for all five selected routes;
3. whole-tranche cost is recomputed from those fresh endpoints and pricing tiers;
4. provider seed decisions are regenerated from fresh `supported_parameters` plus the transport contract state;
5. the owner explicitly approves a spend ceiling covering the recomputed tranche;
6. a separate exact-SHA paid trigger is reviewed under normal acceptance governance and publishes accounting/evidence.

Until then, the safe next action is validation and refinement of the zero-spend harness only.
