# Temporary access tokens

## Purpose

AIMETON needs passwordless temporary access for two controlled scenarios:

1. temporary agents/contractors who need access for a bounded period;
2. marketing/demo outreach where a recipient receives limited trial access without provisioning a permanent password.

A temporary access token is an **entry credential**, not an application session token. A successful token exchange must create the same normal server-side AIMETON session used by password login so that existing role checks, `current_user`, CSRF protection, logout, chat, exports and mission ownership continue to work unchanged.

## Security invariants

- Never store the plaintext token in SQLite, logs, analytics, browser storage or audit events.
- Persist only a cryptographic digest of the token plus metadata.
- Show/copy the plaintext token only once at creation time.
- Token is valid only while all conditions hold: active, not revoked, not expired, and `uses_count < max_uses`.
- Consume a use atomically during successful exchange to prevent concurrent over-use.
- A failed/expired/revoked token exchange must not create a session.
- After exchange, issue the existing `aimeton_session` HttpOnly cookie and `aimeton_csrf` cookie using the same secure/samesite policy as password login.
- Logout revokes only the issued session; administrators can separately revoke the temporary credential.
- Existing user/role authorization remains authoritative. Temporary credentials must not bypass `current_user`, `require_admin`, CSRF or resource ownership checks.
- ADMIN temporary access is forbidden by default for marketing/demo credentials. Any future admin-token capability requires a separate explicit security decision.

## Proposed data model

`temporary_access_tokens`

- `id` integer primary key
- `token_digest` text unique not null
- `subject_user_id` integer not null
- `label` text not null
- `purpose` text not null (`agent`, `marketing_demo`, `support`, `other`)
- `created_by_user_id` integer not null
- `created_at` UTC timestamp not null
- `expires_at` UTC timestamp not null
- `max_uses` integer not null, minimum 1
- `uses_count` integer not null default 0
- `last_used_at` UTC timestamp nullable
- `revoked_at` UTC timestamp nullable
- `revoked_by_user_id` integer nullable
- `revocation_reason` text nullable

The credential should point to a normal active AIMETON user identity. For marketing/demo campaigns, create a bounded-purpose user (normally `USER`) rather than inventing a parallel authorization model.

## Token format

Generate at least 256 bits of entropy using `secrets.token_urlsafe(32)` or stronger. Persist a SHA-256/HMAC digest; never persist the plaintext token.

Recommended external form:

`aimeton_tmp_<random-secret>`

The prefix is for identification only and carries no authorization information.

## API contract

### Admin create

`POST /api/auth/admin/temporary-access-tokens`

Requires:

- authenticated admin;
- existing CSRF protection;
- target `subject_user_id`;
- `expires_at` or bounded TTL;
- `max_uses`;
- `label`;
- `purpose`;
- audit reason.

Response returns metadata plus plaintext `token` **once**.

### Admin list

`GET /api/auth/admin/temporary-access-tokens`

Returns metadata only. Never returns plaintext token or digest.

### Admin revoke

`POST /api/auth/admin/temporary-access-tokens/{token_id}/revoke`

Requires admin + CSRF + reason. Idempotent revoke is preferred.

### Passwordless exchange

`POST /api/auth/token-login`

Body:

```json
{"token":"aimeton_tmp_..."}
```

On success:

1. validate digest and metadata;
2. atomically consume one permitted use;
3. verify subject user is active;
4. revoke any existing session cookie supplied by that browser;
5. create the normal AIMETON session;
6. issue normal session + CSRF cookies;
7. return the standard `UserResponse` plus non-secret temporary-access metadata if useful.

Use generic `401 unauthenticated` for invalid/expired/exhausted/revoked external tokens so the endpoint does not disclose credential state to an attacker.

## Browser UX

Login gate should support two modes:

- **Пароль** — existing username/password flow;
- **Временный доступ** — paste token or consume an explicit invitation link.

For emailed campaigns a link may carry the token once, for example a fragment-based handoff handled by the frontend (`/#access_token=...`) so ordinary server access logs do not receive the secret in the URL query string. The frontend should immediately remove the token from the address bar after exchange and never place it in local/session storage.

A QR code may later encode the same invitation URL; it is still the same credential and subject to TTL/use limits.

## Recommended presets

These are policy defaults, not hard-coded authorization rules:

- temporary agent: 1-7 days, 5-50 successful exchanges depending on operational need;
- individual marketing demo: 24-72 hours, 1-3 successful exchanges;
- event/demo booth: separate campaign-specific user/token model, short TTL and deliberately higher use limit; do not reuse an individual's invitation credential.

## Audit events

Record without secrets:

- token created: id, subject user, purpose, expiry, max uses, actor;
- token successfully exchanged: token id, subject user, resulting session id/reference if safe, use counter, timestamp;
- token revoked: actor, reason, timestamp;
- exhausted/expired status can be derived; optionally emit aggregate events without logging presented token material.

## Tests / acceptance

- plaintext token is returned once and absent from DB/loggable models;
- valid token creates the same cookie/session shape as password login;
- `max_uses=1` succeeds once and then returns 401;
- expiry is enforced at the boundary;
- revoke prevents further exchange;
- concurrent final-use exchanges cannot both succeed;
- blocked/deactivated subject user cannot log in with a previously issued token;
- token login cannot create ADMIN privilege unless the subject already has an explicitly allowed role and policy permits that token purpose;
- CSRF remains required for authenticated mutations after token login;
- logout works identically to password sessions;
- browser does not persist plaintext token;
- invitation URL does not leak the token through query-string server logs/referrers;
- admin listing never returns token or digest.

## Rollout

1. Repository/service + schema + unit tests.
2. Auth API admin issuance/revoke + token exchange.
3. Admin UI for issuing and revoking tokens.
4. Login-gate token mode and invitation-link flow.
5. Stage acceptance with single-use and expired/revoked cases.
6. Marketing automation integration only after Stage security acceptance.
