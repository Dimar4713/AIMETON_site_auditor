# Legacy `/api/analyze` submit handler cleanup

Follow-up after Business Audit Workspace PR #455.

## Current debt

`static/app.js` still owns a legacy `f.onsubmit -> POST /api/analyze` path, while `static/live-analysis.js` captures the same submit event and suppresses the legacy handler with `stopImmediatePropagation()` before starting `POST /api/analyze/start`.

This is currently functional but leaves two owners attached to the same DOM submit lifecycle.

## Cleanup invariant

Do not remove the legacy handler until the async completion path explicitly preserves all compatibility side effects required by the existing UI:

- current `analysis` state;
- `activeAnalysisId` / `ensureAnalysisId`;
- chat-session reset and chat rendering;
- history persistence;
- Markdown/DOCX/PDF export state;
- fallback result rendering if still retained.

## Required regression coverage

Before removal, prove:

1. one form submit creates exactly one analysis request and it is `/api/analyze/start`;
2. `/api/analyze` is not called by the site-audit submit path;
3. async completion preserves `analysis` for `/api/chat`;
4. Markdown and DOCX exports receive the completed `SiteAnalysis`;
5. completed async analysis is persisted to history once;
6. a new analysis resets the previous chat session;
7. completed/degraded/blocked/failed states leave no stuck loading UI;
8. browser resume does not start a second mission or duplicate history;
9. the fallback renderer is either explicitly preserved or removed in the same cleanup change.

## Scope discipline

Keep this cleanup out of PR #455. Perform it as a dedicated follow-up PR after the Business Audit Workspace is accepted on stage.
