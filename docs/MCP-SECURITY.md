# MCP security boundary

## Profiles

- `/mcp/` — public read-only profile;
- `/mcp-admin/` — administrative profile protected by `Authorization: Bearer <token>`;
- `/api/health` remains public for external monitoring.

Public tools:

- `analyze_site`;
- `hunt_companies`;
- `company_intelligence`.

Administrative tools:

- `security_profile` — returns sanitized configuration metadata only.

## Authentication

The admin profile requires the stage secret:

```text
AIMETON_MCP_ADMIN_TOKEN
```

If the secret is absent, the admin endpoint remains locked and returns `401`. Token rotation is controlled by replacing the environment secret and recreating the application container. The old value is revoked immediately after restart.

Tokens are compared with `hmac.compare_digest`. Raw token values are never written to logs. Audit identifies credentials only by a truncated SHA-256 fingerprint.

## Rate and concurrency limits

Stage variables:

- `AIMETON_MCP_PUBLIC_RATE_LIMIT` — public requests per actor/window, default `30`;
- `AIMETON_MCP_ADMIN_RATE_LIMIT` — admin requests per actor/window, default `20`;
- `AIMETON_MCP_RATE_WINDOW_SECONDS` — window length, default `60`;
- `AIMETON_MCP_MAX_CONCURRENCY` — concurrent requests per profile/process, default `4`.

Exceeding the rate returns `429`. Exhausting the short concurrency admission window returns `503`.

The baseline limiter is intentionally in-memory and lightweight for one stage application process. A shared external limiter is required before horizontal scaling to multiple replicas.

## Sanitized audit fields

Each MCP request emits:

- actor fingerprint;
- profile (`public` or `admin`);
- request id;
- result status;
- duration in milliseconds;
- Unix timestamp.

The audit trail does not include:

- bearer tokens or API keys;
- JSON-RPC parameters;
- company names, URLs or user prompts;
- process environment;
- internal network addresses.

## Existing protections retained

- DNS rebinding protection;
- explicit host/origin allowlists without wildcards;
- scraper SSRF protection;
- application input and source limits;
- relative proxy-safe MCP redirects.

## Acceptance checks

Automated tests verify:

- public profile availability without credentials;
- admin rejection for missing/wrong credentials;
- admin acceptance for the configured credential;
- `429` after the configured request limit;
- relative redirects for public and admin endpoints;
- health endpoint availability;
- DNS rebinding and origin protections.
