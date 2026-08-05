# Runtime Time and UMEL Contract — AIMETON Site Auditor

Status: approved local implementation contract
Canonical laws:
- `Dimar4713/aimeton-architecture/docs/standards/RUNTIME_TIME_STANDARD.md`
- `Dimar4713/aimeton-architecture/docs/standards/UMEL.md`

## Runtime Time API

The Site Auditor MUST expose a read-only canonical runtime time endpoint:

`GET /api/runtime/time`

Minimum response contract:

```json
{
  "utc": "2026-08-05T00:00:00.000Z",
  "unix_ms": 0,
  "source": "chrony",
  "synced": true,
  "offset_ms": 0.0,
  "stratum": 2,
  "quality": "trusted"
}
```

Rules:

1. All public timestamps are UTC ISO-8601 with `Z`.
2. `source`, `synced`, `offset_ms`, `stratum` and `quality` are bounded safe projections; raw server configuration and host paths MUST NOT be exposed.
3. Health endpoint `GET /api/runtime/time/health` MUST return `ok`, `degraded` or `failed` based on infrastructure policy thresholds.
4. If canonical synchronization data is unavailable, the service may return a local-clock fallback only with `quality=fallback` and an explicit reason code. It MUST NOT claim trusted time.
5. Mission, trace, log, evidence and report timestamps MUST migrate to a shared clock abstraction; direct ad-hoc clock reads are prohibited in new code.

## MCP contract

The application MCP surface MUST provide a read-only tool compatible with:

`runtime.time()`

It returns the same safe projection as `/api/runtime/time` and does not accept mutation arguments.

## UMEL event contract

Mission progress MUST use stable event codes from the canonical UMEL registry. Icons and localized text are presentation fields; event codes are the durable contract.

Minimum long-mission sequence:

- `mission.received` 🧭
- `goal.resolved` 🎯
- `route.planned` 🗺️
- `research.started` 🔎
- `provider.requested` 🌐
- `provider.responded` 📡
- `data.received` 📦
- `picture.assembled` 🧩
- `analysis.running` 🧠
- `evidence.checked` ⚖️
- `confidence.scored` 📊
- `evidence.saved` 💾
- `journal.updated` 📜
- `stage.completed` ✅
- `mission.completed` 🎉

Exceptional events:

- `external.waiting` ⏳
- `attempt.retrying` ♻️
- `flow.gap_detected` 🚧
- `repair.running` 🩹
- `service.degraded` ⚠️
- `protection.active` 🛡️
- `owner.decision_required` 👤
- `mission.failed` ❌

## UI and trace requirements

1. A user action starting a long mission MUST render a UMEL event within 300 ms.
2. The UI MUST show current stage, elapsed time from canonical UTC, heartbeat and terminal state.
3. Runtime trace stores event code, canonical UTC timestamp, mission/attempt correlation, state and bounded reason code.
4. UI, admin workspace, MCP, logs and exports MUST project the same event code and meaning.
5. Degraded or blocked result MUST NOT be presented as client-ready merely because execution terminated.

## Tactical plan

1. Add shared clock interface and safe chrony status adapter.
2. Implement `/api/runtime/time` and `/api/runtime/time/health` with tests.
3. Add MCP `runtime.time` tool.
4. Add versioned UMEL registry in code.
5. Map current public progress events and trace operations to UMEL codes without losing existing evidence.
6. Implement mission reporter UI and connect it to Issue #339 acceptance criteria.
7. Add exact-SHA stage acceptance for time trust and UMEL progress.

## Acceptance

- UTC is derived from server runtime and matches the host within policy threshold;
- unsynchronized/fallback states are explicit;
- no secret or private path leakage;
- one event code has one canonical meaning across API/UI/trace/MCP;
- delayed, degraded, retry and failure scenarios are covered by API/UI/e2e tests.
