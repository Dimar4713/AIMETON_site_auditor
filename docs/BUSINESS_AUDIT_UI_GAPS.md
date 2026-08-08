# Business audit workspace — verified integration notes

## Verified contracts

- `POST /api/analyze/start` accepts the existing `AnalyzeRequest` (`url`) and returns `mission_id`, `analysis_id`, `state`, `status_url`, and `events_url`.
- `GET /api/analyze/{analysis_id}` returns analysis state plus the final `result` when available.
- `GET /api/analyze/{analysis_id}/events` returns structured real mission events with `phase`, `event_code`, `state`, `icon_key`, `message`, `detail`, `heartbeat`, and `next_action`.
- Analysis runtime terminal states are `completed`, `degraded`, `blocked`, and `failed`; the UI must render only states/events actually returned by the backend.
- `GET /api/user/missions/{mission_id}/report` returns the authenticated user's `SiteAnalysis` report when available.
- `GET /api/user/missions/{mission_id}/records` is authenticated and intentionally exposes a sanitized user projection, not the raw evidence store.
- The repository contains `POST /api/chat`; do not label chat unavailable solely because a constrained sandbox could not reach stage.
- The repository contains preliminary analysis export endpoints; their request body is the `SiteAnalysis` model. Stage integration still needs acceptance after deployment.

## Remaining integration gaps to verify on Stage

- Confirm deployed discovery endpoints (`/llms.txt`, `/api/capabilities`, `/openapi.json`, `/api/docs.txt`) after the latest deployment reaches Stage.
- Confirm the browser authentication/CSRF flow for endpoints that require the owned-mission session.
- Confirm that an async analysis result's `mission_id` maps to an owned mission usable through `/api/user/missions/{mission_id}/report` and `/records`; do not assume this linkage until tested.
- Confirm report/export availability across `completed`, `degraded`, `blocked`, and `failed` outcomes.
- Validate responsive UI, accessibility, and real end-to-end behavior against Stage.

## UX rule

Use backend event semantics directly for the live mission reporter. A presentation layer may group events visually, but it must not invent progress stages or completion percentages not supported by received events.
