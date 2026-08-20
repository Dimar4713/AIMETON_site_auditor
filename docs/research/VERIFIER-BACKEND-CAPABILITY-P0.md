# VERIFIER-P0 · Backend capability qualification

Status: experimental / non-production / first runtime probe completed; score-distribution extraction refinement in progress.

Related: #783, `aimeton-architecture#123`, `Dimar4713/llm-as-a-verifier#1`.

## Mission position

The verifier backend can return token-level logprobs, but Golden-5 showed that `logprobs present` is not equivalent to `usable A-T probability distribution present`. The critical gate is therefore narrower: a score event is probabilistic evidence only when one score position exposes at least two distinct A-T alternatives.

The capability gate is separate from release authority. Passing it only admits a backend to an experiment; it does not grant client release authority and does not override hard, evidence, policy, budget or human-review gates.

## Candidate 1: RouterAI / `openai/gpt-4o-mini`

RouterAI documentation declares support for:

- `logprobs: boolean`;
- `top_logprobs: integer` from 0 to 20 when `logprobs=true`;
- `response_format` and structured outputs on supported routes.

References:

- https://routerai.ru/docs/guides/overview/parameters
- https://routerai.ru/models/openai/gpt-4o-mini

OpenAI documents strict JSON-schema Structured Outputs for GPT-4o-mini-class models. This does not prove RouterAI's exact route exposes constrained top-logprobs, so the behavior is measured rather than assumed.

## Evidence already obtained

Initial live capability run `32413075031` confirmed the exact RouterAI route returns HTTP 200, token-level logprobs and top-logprobs. It was cheap and fast enough for P0 experimentation.

The first Golden-5 run `32416294981` then exposed the more important limitation:

- provider attempts: `144`;
- provider successes: `144`;
- score responses with logprobs: `96 / 96`;
- score events with at least two distinct A-T alternatives: `86 / 96`;
- estimated provider cost: `3.487929 RUB`.

The ten rejected events were not provider outages. Generic top-20 alternatives sometimes contained only one A-T score token because unrelated tokens occupied the remaining top-logprob slots. Renormalizing that singleton would create a point estimate, not a measured distribution, so AIMETON correctly failed closed.

## Refined runtime qualification contract

A backend score path is `runtime_qualified` only when all of the following are measured:

1. `choices[0].logprobs.content` exists;
2. at least one token position contains `top_logprobs`;
3. at least one A-T verifier score token is visible;
4. at least **two distinct A-T alternatives occur at the same score position**;
5. finite logprobs exist for the response;
6. evidence can be normalized without inventing neutral `0.5` or treating singleton support as a probability distribution.

Equal probabilities across A-T alternatives are valid probabilistic support; they are not considered degenerate merely because the distribution is flat. A singleton A-T support is `runtime_degraded` even if many unrelated tokens carry different logprob values.

## Constrained-decoding experiment

The next probe performs two bounded requests against the same model route:

1. **unconstrained**: direct one-letter A-T request with `top_logprobs=20`;
2. **structured**: strict `response_format=json_schema` whose `score` field is an enum of exactly A through T, also with `top_logprobs=20`.

The question is empirical: does constrained decoding cause the score position's top-logprobs to expose multiple A-T alternatives instead of allowing non-score tokens to consume the top-20 list?

Overall qualification is granted only if the structured path exposes at least two distinct A-T alternatives. Both responses are sanitized; raw provider bodies and API keys are not retained.

## Spend boundary

The owner authorized VERIFIER-P0 provider/model spend up to **100 RUB**. The structured capability experiment admits exactly two very small requests and preflights a conservative token upper bound before either is sent. Expected cost is far below the owner ceiling.

No provider call occurs during ordinary PR CI. Live calls remain available only through the owner-admitted command path on #783 after exact-head CI and merge.

## Safety invariant

**Verifier != Truth.** A successful structured score-distribution probe would only unblock further calibration. It cannot override deterministic tests, evidence/provenance failures, OCC-49/policy restrictions, release gates or mandatory HITL.

## Next critical step

1. land the strengthened score-support qualification and two-mode capability probe after provider-free CI;
2. execute one owner-admitted probe on #783;
3. if structured A-T support qualifies, update the fork/Site Auditor integration so Golden-5 uses the constrained score path and rerun the bounded calibration;
4. if structured support still fails, do not weaken the two-score floor — test another extraction mechanism/provider/model instead.
