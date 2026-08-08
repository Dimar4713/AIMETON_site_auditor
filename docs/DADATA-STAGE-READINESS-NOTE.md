# DaData Stage readiness hardening

The Configure DaData Stage smoke treats container health as necessary but not sufficient for public reverse-proxy readiness. Live health and lookup endpoints use bounded retry/backoff after container replacement. Credential validation remains strict; retries only cover transient public-route readiness.

Acceptance:
- no secret values are logged;
- current DaData health contract is asserted directly in the committed script;
- lookup must return a typed registry-mirror state and response digests for returned records;
- readiness retries are bounded and fail closed after the configured attempt count;
- workflow validates the committed smoke script instead of mutating it at runtime.
