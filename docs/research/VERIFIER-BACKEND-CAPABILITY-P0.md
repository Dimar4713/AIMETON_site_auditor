# VERIFIER-P0 · Backend capability qualification

Status: experimental / non-production / capability code merged; measured provider qualification pending.

Related: #783, `aimeton-architecture#123`, `Dimar4713/llm-as-a-verifier#1`.

## Mission position

The offline verifier scaffold and backend capability contract are already in `main`. The next critical gate is to prove that a concrete backend can expose usable token-level probability evidence before any semantic-verifier calibration is treated as measured.

The capability gate is separate from release authority. Passing it only admits a backend to an experiment; it does not grant client release authority and does not override hard, evidence, policy, budget or human-review gates.

## Candidate 1: RouterAI

Site Auditor already uses RouterAI through an OpenAI-compatible `/chat/completions` API. RouterAI documentation currently declares support for:

- `logprobs: boolean`;
- `top_logprobs: integer` from 0 to 20 when `logprobs=true`;
- structured output / response format on supported routes.

Authoritative documentation used for the contract-level qualification:

- https://routerai.ru/docs/guides/overview/parameters
- https://routerai.ru/models/openai/gpt-4o-mini

This is enough to classify RouterAI as `contract_candidate`, but not enough to classify a specific model/provider route as `runtime_qualified`.

## Runtime qualification contract

A live probe must be tiny and bounded. It requests at most four output tokens with `logprobs=true` and `top_logprobs=20`.

A backend is `runtime_qualified` only when all of the following are measured in the actual response:

1. `choices[0].logprobs.content` exists;
2. at least one token position contains `top_logprobs`;
3. at least one A–T verifier score token is visible in the returned alternatives;
4. finite logprob values are non-degenerate;
5. the response can be normalized without inventing neutral `0.5` evidence.

Missing logprob content is `runtime_incapable`. Missing score tokens, missing top alternatives or a degenerate distribution is `runtime_degraded`. Neither state may enter calibration as a measured result.

## Current evidence matrix

| Measure | RouterAI state | Evidence |
|---|---|---|
| Existing AIMETON integration | confirmed | `app/llm.py`, `app/routerai_strict_request.py` |
| OpenAI-compatible chat endpoint | confirmed in source | `https://routerai.ru/api/v1/chat/completions` |
| `logprobs` documented | confirmed | RouterAI parameters documentation |
| `top_logprobs` documented | confirmed | RouterAI parameters documentation |
| `openai/gpt-4o-mini` current published token price | confirmed snapshot | RouterAI model page; 15 RUB / 1M input, 61 RUB / 1M output at the 2026-08-20 check |
| exact model/provider route returns usable top-logprobs | **not yet measured** | owner-admitted bounded live probe |
| A–T score-token extraction on actual route | **not yet measured** | owner-admitted bounded live probe |
| non-degenerate distribution on actual route | **not yet measured** | owner-admitted bounded live probe |

## Owner spend authorization and control path

On 2026-08-20 the owner explicitly authorized verifier P0 provider/model spend up to **100 RUB**.

The authorized execution slice is intentionally narrower than that ceiling:

- exactly one RouterAI request per command;
- exact model locked to `openai/gpt-4o-mini`;
- fixed probe payload with `max_tokens=4`;
- current published RouterAI price snapshot: 15 RUB / 1M input tokens and 61 RUB / 1M output tokens;
- conservative preflight assumes at most 2048 input tokens plus four output tokens, which is far below the 100 RUB ceiling;
- raw provider response and API key are not retained in evidence;
- only sanitized capability, usage, latency and estimated-cost fields are published;
- failed or degraded capability still produces sanitized evidence and then fails closed.

The owner-only execution route is introduced by #789:

```text
/ probe command on #783
→ central AIMETON Command Router
→ workflow_dispatch only
→ repository-scoped self-hosted stage runner
→ stage environment ROUTERAI_API_KEY
→ exactly one bounded RouterAI call
→ sanitized evidence back to #783
→ runtime qualification gate
```

The command is authorized only on #783 and carries machine-readable inputs `allow_paid_calls=true`, `owner_spend_authorized=true`, `max_budget_rub=100` and the exact model id.

## Safety / spend boundary

No provider call is performed by ordinary CI, by the capability module, or by tests. The paid request can happen only through the owner-admitted workflow after its code is merged to `main`.

The probe does not deploy production code, does not call search providers, does not mutate release state and does not automatically begin Golden-5 calibration.

## Next critical step

After #789 is green and merged, execute one owner-admitted probe against RouterAI `openai/gpt-4o-mini`, read back the sanitized runtime evidence and classify the route:

- `runtime_qualified` → proceed to bounded Golden-5 calibration;
- `runtime_incapable` / `runtime_degraded` → retain evidence, keep calibration blocked, test the next backend candidate rather than weakening the gate.
