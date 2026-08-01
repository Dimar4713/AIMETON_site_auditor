# AIMETON Site Auditor — Service Capability Policy v0.1

## Purpose

The Web UI is composed from effective capabilities rather than a fixed list of all backend functions. Availability depends on authentication, role, plan entitlement, quota, ownership and runtime state.

This document defines the application contract for the simplified MVP and the later migration to the AIMETON Supabase platform.

## Independent access axes

- `authentication`: who the user is;
- `authorization`: what the role may do;
- `entitlement`: which services the account or organization has purchased;
- `quota`: how much remains;
- `runtime_gate`: whether the operation is currently safe and technically possible;
- `evidence_gate`: whether the result may be released.

Role and plan are never interchangeable.

## MVP subjects

Roles:

- `admin`;
- `user`.

Initial plan:

- `test`.

The MVP has no self-registration, billing or organizations. The policy contract is nevertheless organization-ready and replaceable through an adapter.

## MVP capability catalog

User capabilities:

- `analyze_site`;
- `view_own_missions`;
- `view_own_evidence`;
- `view_own_sufficiency`;
- `view_released_report`;
- `chat_with_own_mission`.

Admin capabilities:

- all user capabilities;
- `manage_local_users`;
- `view_all_missions`;
- `view_diagnostics`;
- `view_provider_health`;
- `retry_mission`;
- `set_test_limits`.

Candidate later services, disabled by default until product readiness is proven:

- `company_intelligence`;
- `company_hunt`;
- `sef_company_profile`;
- `sef_report`;
- `evidence_review`;
- `compare_companies`;
- `api_access`;
- `mcp_access`.

Presence of an endpoint does not automatically enable its capability.

## Required interfaces

```python
class CapabilityPolicy(Protocol):
    def evaluate(self, context: CapabilityContext, capability: str) -> CapabilityDecision: ...

class UsageRepository(Protocol):
    def reserve(self, subject_id: str, capability: str, idempotency_key: str) -> UsageReservation: ...
    def commit(self, reservation_id: str) -> None: ...
    def release(self, reservation_id: str) -> None: ...
```

`CapabilityPolicy` must remain independent from FastAPI routes and frontend components. The first adapter may use local configuration and persistence; the future adapter will use Supabase tables and RLS-aware organization context.

## Capability endpoint

The authenticated UI receives a server-calculated response, for example:

```json
{
  "policy_version": "0.1.0",
  "role": "user",
  "plan_code": "test",
  "capabilities": {
    "analyze_site": {
      "allowed": true,
      "remaining": 7,
      "limit": 10
    },
    "company_hunt": {
      "allowed": false,
      "reason": "feature_not_entitled"
    },
    "manage_local_users": {
      "allowed": false,
      "reason": "role_not_allowed"
    }
  }
}
```

The UI uses this response to build navigation, buttons, upgrade hints and limit indicators.

## UI display rules

- Hide internal/admin operations from ordinary users.
- Show higher-plan commercial services as locked cards when useful for packaging.
- Show remaining quota for metered services.
- Show temporary provider/system degradation with an explicit explanation.
- Never show a released-report action when Report Gate forbids release.

## Backend enforcement

Every protected API operation must evaluate the policy again. Frontend hiding is not authorization.

Typed outcomes:

- `401 unauthenticated`;
- `403 role_not_allowed`;
- `403 feature_not_entitled`;
- `403 resource_not_owned`;
- `409 quota_exhausted`;
- `409 system_degraded`;
- `409 sufficiency_gate_blocked`.

No service-role secret, local password hash, provider secret or internal policy override may reach browser responses.

## Quota rules

- Reserve quota before expensive work.
- Use an idempotency key per logical user operation.
- Commit usage only according to the service accounting rule.
- Release a reservation when execution did not start.
- Retry must not double-charge.
- Admin retry policy must be explicit and auditable.

The MVP may use simple counters, but the contract must support a later append-only usage ledger.

## Relation to mission ownership

A capability decision does not replace ownership checks. A user with `view_own_missions` can access only missions where `owner_id` matches the authenticated subject. Admin cross-user access requires `view_all_missions` and must produce an audit event.

## Relation to evidence and report gates

Paid access cannot promote hypotheses to facts or bypass sufficiency requirements. `sef_report` entitlement means the service may be requested; actual report release still requires Evidence Guard and Report Gate.

## MVP delivery sequence

1. Define capability codes and local plan configuration.
2. Add `CapabilityPolicy` and typed decisions.
3. Add authenticated `/api/me/capabilities`.
4. Enforce policy on user/admin endpoints.
5. Build UI navigation from effective capabilities.
6. Add quota reservation/idempotency for expensive operations.
7. Add negative role, ownership and quota tests.
8. Produce a migration map to platform Supabase entitlements.

## Acceptance criteria affected

For issue #145:

- simplified user/admin UI is capability-driven;
- ordinary users cannot call admin operations directly;
- unavailable services have typed reasons;
- test quotas are displayed and enforced;
- direct endpoint calls cannot bypass the policy;
- Report Gate remains independent from tariff access;
- local adapters can later be replaced by Supabase implementations.

For issue #144:

- the future Supabase adapter preserves capability codes and API contracts;
- organization plans, memberships and RLS replace local subject configuration without rewriting domain operations.
