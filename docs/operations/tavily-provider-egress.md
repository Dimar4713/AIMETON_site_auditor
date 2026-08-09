# Tavily provider egress and compliance controls

## Purpose

This document defines how AIMETON Site Auditor configures and validates the Tavily Search provider without making Tavily a mandatory dependency and without mixing technical reachability with contractual permission.

## Runtime variables

- `TAVILY_TOKEN` or `TAVILY_API_KEY` — Tavily API credential. Secrets only; never commit.
- `TAVILY_SEARCH_COST_USD` — modeled cost per SearchGateway provider call used for mission accounting.
- `TAVILY_PROXY_URL` — optional provider-local HTTP/HTTPS proxy URL. When absent, Tavily uses direct outbound networking. This setting applies only to the Tavily adapter.
- `TAVILY_CONTRACT_ALLOWED` — explicit execution gate. `false` makes the Tavily adapter unavailable before network execution and before paid cost reservation.
- `SEARCH_CONCURRENCY_TAVILY` — Tavily-local concurrency ceiling.
- `SEARCH_JITTER_TAVILY_MIN_SECONDS` / `SEARCH_JITTER_TAVILY_MAX_SECONDS` — bounded provider-local jitter.
- `SEARCH_QUOTA_TAVILY` — optional runtime call quota.

## Current development egress evidence

A Netherlands proxy purchased for development was tested from the Stage VPS against a neutral IP echo service:

- HTTP/HTTPS: `51.241.23.14:50100` — works;
- SOCKS5: `51.241.23.14:50101` — works;
- observed egress in both cases: `51.241.23.14`;
- proxy authentication was not required because the service accepted the Stage VPS through IP allowlisting.

The proxy password supplied temporarily by the owner is not stored in the repository, documentation, workflow, issue or logs.

## Important contract boundary

Technical proxy readiness is not the same thing as authorization to call a provider through that route.

Tavily Platform Terms dated 2026-05-04 contain export/sanctions restrictions that currently make live Tavily use associated with Russia a compliance question. Therefore:

1. provider-specific proxy support is implemented and tested as infrastructure capability;
2. `TAVILY_CONTRACT_ALLOWED` can block Tavily before a network call;
3. live Tavily traffic through an alternate regional egress must only be enabled in an execution context that is permitted by applicable law and Tavily's contract or explicit written provider authorization;
4. the proxy must not be used to conceal AIMETON identity or evade a provider restriction.

## Validation sequence

1. Verify `TAVILY_TOKEN` exists without printing it.
2. Verify `TAVILY_SEARCH_COST_USD` is non-zero before enabling paid SearchGateway execution.
3. Validate proxy transport, if used, against a neutral endpoint and record only egress IP / latency / success state.
4. Run Tavily adapter contract tests with `httpx.MockTransport`.
5. Run SearchGateway tests for budget, quota, circuit and fallback behavior.
6. Confirm `TAVILY_CONTRACT_ALLOWED` for the actual deployment/customer context.
7. Only then perform a minimal live Tavily preflight and record provider call count and cost.
8. For benchmark runs, record query set, provider calls, modeled/actual-known cost, latency, result count, unique domains and quality gain.

## Failure semantics

- Missing token or disabled contract gate: no Tavily network call.
- Missing/unknown price for paid SearchGateway use: fail closed through normal SearchGateway pricing guard.
- 401/403: `provider_blocked`.
- 429: `rate_limited`.
- timeout: `timeout`.
- provider failures feed the existing circuit breaker and fallback strategies.

## Security

Provider errors and SearchGateway diagnostics must never include:

- Tavily token;
- proxy username/password;
- full proxy URL if it contains credentials;
- authorization headers.

The proxy is a routing capability, not a credential source and not a substitute for provider authorization.
