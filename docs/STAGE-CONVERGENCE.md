# Stage convergence and long-mission admission

Status: implementation contract for issue #693.

## Why this exists

A successful `Deploy Stage` is not by itself proof that the Stage runtime is safe for a long asynchronous mission. Field Better DeepSeek acceptance on 2026-08-15 proved that a post-deploy configurator could recreate `aimeton-auditor` after the deploy workflow had already succeeded, which interrupted an active MCP mission with HTTP 502.

The immediate DaData race was fixed in #692. This document defines the wider convergence boundary so future agents and acceptance jobs do not infer stability from the deploy job alone.

## Canonical automatic convergence topology

For one exact application SHA, Stage is `converged` only after all of these have succeeded:

1. `Deploy Stage` — installs the exact source bundle and performs the primary container recreate/health smoke.
2. `Configure DaData Stage` — parallel post-deploy provider reconcile; unchanged material must be verify-only.
3. `Runtime Persistence Reconcile` — verifies persistent `/app/data`; performs a controlled recreate only when the invariant is broken.
4. `Stage Auth Persistence Guard` — verifies persistent auth and live admin login; repairs auth data only when the invariant is broken.
5. `Stage Convergence` — **starts from the successful `Deploy Stage` event in parallel with the post-deploy branches**, waits until DaData + Runtime Persistence + Auth Guard for the same exact SHA have completed successfully, then re-verifies live exact SHA/runtime health/persistence/auth/DaData and atomically publishes the convergence marker.

The convergence workflow is intentionally triggered from `Deploy Stage`, not from `Stage Auth Persistence Guard`. GitHub Actions limits `workflow_run` chains to three levels; the existing `Baseline → Deploy → Runtime Persistence → Auth Guard` path already reaches that limit. Starting convergence from Deploy keeps the workflow within the supported depth while preserving the requirement that marker publication waits for all downstream gates.

`Stage Convergence` is the only workflow in this topology allowed to publish the machine-readable `converged` state.

## Restart-aware marker

Canonical host/container path:

`/opt/aimeton/auditor-stack/data/runtime-core/stage-convergence.json` ↔ `/app/data/stage-convergence.json`

The marker contains no secrets. It binds:

- exact deployment SHA;
- an opaque `runtime_instance_id` generated when the application process starts;
- UTC convergence time;
- workflow run ids for the required gates;
- boolean evidence checks.

The public runtime projection compares the persistent marker with the currently running process. Therefore:

- new application SHA → old marker becomes `stale`;
- container/process recreate on the same SHA → old marker becomes `stale` because `runtime_instance_id` changes;
- missing marker → `pending`;
- malformed/incomplete marker → `invalid`;
- only exact SHA + exact current instance + all checks true → `converged`.

This makes the marker self-invalidating after a restart even if a manual repair workflow forgets to delete the persistent file.

## Agent-visible admission check

Read-only interfaces:

- REST: `GET /api/runtime/convergence`
- MCP: `runtime.convergence`

A browser/LLM agent should call `runtime.convergence` before starting a long mission whose result would be harmed by an unexpected Stage restart. `analysis.start` remains backward compatible and is not blocked server-side by this first implementation layer.

Recommended agent contract:

1. call `runtime.convergence`;
2. require `state=converged` for long mission admission;
3. start `analysis.start`;
4. use `analysis.status/events` with increasing `poll`;
5. if a later `runtime.convergence` becomes `stale`, treat the runtime as restarted and do not assume in-process mission continuity.

## Mutator inventory

### Automatic post-deploy mutators/checks

| Workflow | Trigger | Container impact | Convergence role |
|---|---|---|---|
| Deploy Stage | successful main Baseline CI / manual deploy path | expected primary recreate | required root gate |
| Configure DaData Stage | `workflow_run: Deploy Stage` | conditional recreate only when DaData material changes | required parallel gate |
| Runtime Persistence Reconcile | `workflow_run: Deploy Stage` | conditional recreate only when persistence invariant is broken | required gate |
| Stage Auth Persistence Guard | `workflow_run: Runtime Persistence Reconcile` | normally verify-only; may mutate auth DB when invariant is broken | required terminal gate |
| Stage Convergence | `workflow_run: Deploy Stage` | verify-only; waits for all required gates and publishes marker | admission gate |

### Explicit/manual repair or provisioning paths

These are **not** part of normal automatic convergence and must not be silently treated as such:

| Workflow/path | Trigger | Potential impact |
|---|---|---|
| Provision Stage MCP Admin Token | `workflow_dispatch` | force-recreates auditor when provisioning/rollback occurs |
| Stage Data Mount Reconcile | `workflow_dispatch` with exact SHA | force-recreates auditor |
| Server Auth Persistence Migration | `workflow_dispatch`; `apply` requires explicit confirmation | stops/recreates/restarts auditor |
| Configure Yandex Search Stage | manual dispatch or dedicated main trigger file | rebuilds/recreates auditor |

Any path that recreates/restarts the application automatically invalidates an existing convergence marker through runtime-instance mismatch. After intentional maintenance, `Stage Convergence` must be run again before long-mission admission.

## Security and evidence rules

The convergence marker and public projection must never contain:

- API keys or tokens;
- cookies or auth headers;
- passwords;
- prompts, model chain-of-thought, provider payloads;
- internal secret values.

Allowed evidence is limited to exact SHA, opaque runtime instance id, UTC time, workflow run ids, boolean invariant checks and sanitized state.

## Next layer: durable mission resume

This marker solves admission and stale-runtime detection. It does **not** make current in-process async analysis durable across a real restart. The next #693 slice must persist enough mission state to recover `MISSION / DONE / DOING / NEXT / BLOCKED / INVARIANTS` or introduce a restart admission gate that delays destructive maintenance while non-resumable missions are active.
