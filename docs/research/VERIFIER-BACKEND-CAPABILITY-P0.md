# VERIFIER-P0 · Backend capability qualification

Status: experimental / non-production / no provider call executed by this change.

Related: #783, `aimeton-architecture#123`, `Dimar4713/llm-as-a-verifier#1`.

## Mission position

The offline verifier scaffold is already in `main`. The next critical gate is to prove that a concrete backend can expose usable token-level probability evidence before any semantic-verifier calibration is treated as measured.

The capability gate is separate from release authority. Passing it only admits a backend to an experiment; it does not grant client release authority and does not override hard, evidence, policy, budget or human-review gates.

## Candidate 1: RouterAI

Site Auditor already uses RouterAI through an OpenAI-compatible `/chat/completions` API. RouterAI documentation currently declares support for:

- `logprobs: boolean`;
- `top_logprobs: integer` from 0 to 20 when `logprobs=true`;
- structured output / response format on supported routes.

Authoritative documentation used for the contract-level qualification:

- https://routerai.ru/docs/guides/overview/parameters

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
| exact model/provider route returns usable top-logprobs | **not yet measured** | requires bounded live probe |
| A–T score-token extraction on actual route | **not yet measured** | requires bounded live probe |
| non-degenerate distribution on actual route | **not yet measured** | requires bounded live probe |

## Safety / spend boundary

No model/provider request is performed by the capability code or tests. `build_openai_logprob_probe_payload()` only constructs the payload offline.

The first live probe is a provider/model invocation and therefore remains behind the existing admission/budget rule. It must not be launched merely because RouterAI is documented as compatible.

## Next critical step

After this capability gate is merged and green, execute one explicitly admitted minimal probe against the chosen RouterAI model/provider route, save the sanitized response capability evidence, and only then start Golden-5 calibration. If RouterAI fails the measured gate, test the next backend candidate rather than weakening the gate.
