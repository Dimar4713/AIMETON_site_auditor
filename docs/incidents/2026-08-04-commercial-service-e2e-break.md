# Commercial service E2E break — 2026-08-04

## User-observed symptoms

- search services return low-information results;
- hunter shows a company list containing mostly names;
- candidate cards are not interactive;
- a discovered company cannot be transferred into company intelligence;
- entering the discovered company manually often produces no useful enrichment.

## Confirmed UI defect

`static/service-catalog.js` renders hunter candidates through `appendItem(...)` as static `article` elements. No candidate action, link, stable identifier, URL/region transfer, or handoff to the company-intelligence form exists.

Therefore the current path ends at:

`hunter response → static title card`

instead of:

`hunter response → candidate entity → explicit “Исследовать” action → prefilled company intelligence request → evidence-bearing mission`.

## Separation of concerns

- UI handoff defect: fix immediately as a bounded P0 slice.
- low-quality/empty external data: diagnose through #293 provider trace and fix only after the selected/called/returned/accepted/used waterfall is observable.

## Acceptance

- every candidate has a visible explicit research action;
- action transfers company name, URL when present, and region;
- company-intelligence panel opens and focuses the form;
- no analysis starts without explicit user submission;
- candidate URL is visible and safely linkable when valid;
- no secrets or provider payloads are exposed.
