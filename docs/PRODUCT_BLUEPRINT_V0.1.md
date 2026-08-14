# Hunter Product Blueprint v0.1

**Status:** working product contract  
**Date:** 2026-08-15  
**Parent:** #660  
**Design issue:** #661

## 1. Product mission

Hunter is not sold as a search endpoint. It is a persistent working environment that helps a B2B commercial/research user turn a vague market-search task into a verified, editable, reusable and repeatable working set of target companies.

The product is ready for marketing only after the user can complete the value path without a developer and the result survives logout/restart/rerun.

## 2. Working customer pain hypothesis

A B2B commercial employee or manager spends hours or days to:

1. formulate where to search;
2. collect candidate companies from many sources;
3. remove duplicates and irrelevant organizations;
4. verify geography, industry and direct/official sources;
5. decide which companies deserve attention;
6. keep notes and manual corrections;
7. turn the research into a shortlist for real sales work;
8. repeat the search later and understand what changed.

Today this work is commonly fragmented across browser tabs, spreadsheets and notes. The expensive part is not one web query; it is maintaining a trustworthy working state and reproducing the reasoning later.

### Hypothesis to validate

The primary pain is reduced when the user receives a durable, evidence-backed shortlist faster than by the current manual workflow and can return later to update it without rebuilding the research from zero.

### Pain metrics to validate with real users

- manual hours per research task;
- time to first useful shortlist;
- number of sources/tabs/files involved;
- percentage of candidates requiring manual verification;
- percentage of stale/duplicate/irrelevant rows;
- effort required to repeat the same research after 1–4 weeks;
- lost context: inability to explain why a company was included/excluded;
- handoff effort from researcher to salesperson/manager.

No ICP or willingness-to-pay conclusion is considered proven until these metrics are tested with real workflows.

## 3. Actors

### Operator / end user

Creates and runs missions, inspects evidence, edits decisions, saves shortlists, reruns and exports results.

### Buyer

Person responsible for the commercial/research process and productivity outcome. May be the operator in a small company or a manager in a larger team.

### Payer

Person/company authorizing spend. Payer is not assumed to be the daily operator.

### Administrator

Controls users, roles, provider/search policies, quality thresholds, tariff/entitlement limits, usage/cost observability and support actions.

## 4. AS-IS business process

Typical manual process:

```text
business question
  -> search engine / directories / registries / maps
  -> copy candidates into spreadsheet
  -> open sites manually
  -> remove duplicates
  -> verify region / industry / relevance
  -> add notes
  -> rank by intuition
  -> send spreadsheet / list
  -> forget exact search path and evidence
  -> repeat much of the work from zero later
```

Observed structural defects:

- no durable mission object;
- query history is separated from final business result;
- evidence and decision are weakly linked;
- manual corrections overwrite rather than augment machine conclusions;
- no explicit rerun lineage;
- no first-class delta between runs;
- handoff often loses provenance;
- cost and quality are difficult to attribute to a particular mission.

## 5. TO-BE business process

The target process is conversational and iterative rather than a one-shot search form.

```text
Workspace / Project
  -> describe business need in natural language
  -> AI consultant clarifies goal / criteria / output form / research depth when needed
  -> versioned Mission Brief
  -> choose usage level: Preset / Guided / Professional Constructor
  -> run Search / Analysis iteration
  -> observe progress
  -> inspect intermediate findings + gaps + evidence
  -> user feedback: narrow / broaden / deepen / change form
  -> revised Mission Brief / configuration
  -> reuse retained evidence where possible
  -> run additional governed research only when needed
  -> inspect Candidate Companies + Evidence
  -> qualify / reject / defer
  -> add notes / manual overrides
  -> assemble Saved Shortlist
  -> export / hand off
  -> return later
  -> rerun / update / deepen
  -> compare new run vs previous run
  -> preserve old decisions, dialogue and evidence
  -> update shortlist
```

The loop continues until the result is acceptable by **content, form and depth**, not merely until a provider call completes.

### User-visible search intent

The user selects the goal, not technical coefficients:

- **Auto** — AIMETON chooses the tactic from observed state;
- **Крупная рыба** — prioritize the strongest/high-confidence candidates;
- **Баланс** — balance shortlist quality and breadth;
- **Золотой песок** — search deeper for rare or easy-to-miss candidates.

Technical thresholds remain administrator-owned policy.

## 5.1 Three-level usage architecture

Hunter SHALL expose three levels of interaction over the same canonical mission, evidence and execution model.

### Level 1 — Preset / One-click

For the mass user who wants the result, not the mechanics.

- choose a ready business service;
- provide minimum context;
- one primary launch action;
- receive a saved evidence-backed result;
- default search strategy, depth, output form and resource envelope come from a versioned accepted preset.

Examples:
- find strongest target companies in a region;
- map competitors;
- find suppliers;
- refresh a saved list and show changes.

### Level 2 — Guided / Tunable

For a user who wants to influence the task without designing the workflow.

- start from a preset or simple Mission Brief;
- use AI consultant to clarify goal;
- tune geography, industry, include/exclude, intent, depth, output form and bounded scope;
- review intermediate findings;
- narrow, broaden or deepen the mission;
- keep all clarification history and Mission Brief revisions.

### Level 3 — Professional Constructor

For analysts, researchers, integrators and power users.

- compose research stages/capabilities;
- configure source/provider roles inside allowed policy;
- define evidence targets, checkpoints and stop/refine logic;
- define output schema;
- configure resource/cost envelope within entitlement;
- save reusable professional recipes;
- promote proven recipes into versioned mass-market presets after evidence and acceptance.

Professional mode MUST NOT bypass security, tenancy, budget, provider or execution governance.

### Progressive disclosure

The same mission can move deeper without losing context:

`Preset -> Настроить -> Guided -> Профессиональный режим -> Constructor`.

All three levels resolve into the same canonical configuration and run through the same validation/policy/execution core.

Reference: `docs/THREE_LEVEL_USAGE_ARCHITECTURE_V0.1.md` and architecture ADR-019.

## 6. Product state model

### Workspace

Container for one user's/team's commercial or research context.

Minimum fields:
- id;
- owner/tenant;
- name;
- status;
- created/updated timestamps.

### Project

Optional grouping of related missions, e.g. market, customer campaign or research topic.

### Research Mission

Durable statement of the business task.

Minimum fields:
- mission id;
- workspace/project id;
- title;
- target industry/category;
- target geography;
- include/exclude criteria;
- requested search intent;
- lifecycle state;
- created by;
- timestamps.

Mission is mutable as a business object, but historical runs retain the exact mission snapshot used for execution.

### Mission Brief revision

Versioned formalization of the current task produced by user input and consultation.

Stores:
- business objective;
- success criteria;
- content requirements;
- output contract;
- research depth;
- constraints;
- accepted scope changes;
- relation to prior revision.

### Consultation Thread / Dialogue Turn

Mission-relevant dialogue is durable state and provenance, not transient UI decoration.

### Resolved Configuration Snapshot

The normalized execution configuration produced from a preset, guided controls or professional constructor.

Every Search Run references the exact resolved configuration used.

### Service Preset / Preset Version

A published, accepted, versioned configuration for one-click use.

Lifecycle: `draft -> tested -> accepted -> published -> deprecated -> retired`.

### Professional Recipe / Recipe Version

Reusable expert configuration that can be rerun, shared where entitled, and potentially promoted into a preset after acceptance.

### Search Run

Immutable execution/version of a mission.

Minimum fields:
- run id;
- mission id;
- parent/prior run id when rerun;
- mission snapshot / brief revision;
- resolved configuration snapshot;
- requested and effective regime;
- source code/deployment identity where useful for provenance;
- started/completed timestamps;
- execution state;
- cost/usage summary;
- quality/funnel summary.

### Candidate Company

Business entity presented to the user. Candidate identity must survive reruns where possible and should not be reduced to one transient URL.

Minimum fields:
- candidate/company id;
- canonical name;
- primary domain/site;
- geography;
- industry classification/signals;
- source role;
- run membership;
- machine qualification state.

### Evidence / Source

Evidence supporting a candidate or claim.

Minimum fields:
- evidence id;
- candidate id;
- run id;
- source/provider role;
- URL/reference;
- captured claim/snippet/metadata as permitted;
- timestamp;
- provenance link;
- confidence/verification state.

### Qualification Decision

Separate the machine recommendation from the user's decision.

Suggested states:
- unreviewed;
- qualified;
- rejected;
- deferred;
- needs_research.

Store:
- machine state/reason;
- user state/reason;
- decision actor;
- timestamp.

### User Note / Manual Override

Manual knowledge must augment the result rather than disappear on rerun.

Store notes and overrides as first-class records with actor/time/provenance.

### Saved Result Set / Shortlist

Named working basket of selected companies, independent from one Search Run.

A shortlist may contain candidates from several runs and preserve user ordering/tags/notes.

### Run Comparison / Delta

First-class relation between two runs.

At minimum classify:
- new candidate;
- still present;
- no longer found;
- evidence changed;
- machine qualification changed;
- user decision unchanged/changed.

Absence in a later search does not delete historical data.

### Export / Handoff

Record what was exported, when, by whom and from which shortlist/run state. Supported output formats may evolve, but export provenance must remain reconstructable.

### Audit Trail

Security- and business-relevant mutations must be attributable to actor/time/object without turning ordinary user activity into opaque mutable state.

## 7. Lifecycle states

### Mission

`draft -> ready -> running -> review -> active -> archived`

Possible failure/interruption states are represented separately from business lifecycle.

### Search Run

`queued -> running -> completed | failed | cancelled`

Runs are immutable after execution except for attached annotations/evidence processing whose history is itself auditable.

### Candidate review

`unreviewed -> qualified | rejected | deferred | needs_research`

User state is not overwritten by a later machine rerun.

## 8. Required operations before product acceptance

The user must be able to:

- create mission;
- save draft;
- clarify mission through AI dialogue;
- edit mission before run;
- choose/open a preset;
- switch from preset to guided without losing context;
- switch from guided to professional constructor without losing context;
- save/reuse a professional recipe;
- execute mission;
- observe progress/status;
- open completed run;
- inspect evidence;
- filter/sort candidates;
- qualify/reject/defer;
- add/edit notes;
- add/remove candidate from shortlist;
- save named shortlist;
- duplicate mission;
- rerun/update/deepen mission;
- compare runs;
- preserve manual decisions across reruns;
- archive/restore where applicable;
- export/handoff;
- return after logout/restart and recover the same state.

## 9. UX information architecture v0.1

### Dashboard

Shows active projects/missions, status, last run, saved shortlist count and next useful action.

Also exposes a catalog of one-click services/presets as the simplest entry point.

### New Mission / Service Entry

Three progressive entry paths:
1. **Ready service** — select preset and launch with minimum context;
2. **Настроить** — guided mission with AI consultant and bounded controls;
3. **Профессиональный режим** — constructor for reusable research recipes.

### Mission Workspace

Persistent screen with:
- Consultation / AI consultant;
- Mission Brief;
- Runs;
- Candidates;
- Shortlists;
- Notes/Activity;
- Exports;
- Configuration summary / recipe where applicable.

### Running Mission View

Human-readable progress events rather than a spinner only:
- planning;
- querying providers;
- collecting results;
- verifying candidates;
- qualifying;
- refinement observation;
- finalizing.

### Candidate List

Needs:
- filters;
- sorting;
- qualification controls;
- evidence indicators;
- direct/official signal;
- region/industry evidence;
- notes;
- shortlist action;
- bulk actions only where reversible/auditable.

### Candidate Card

Shows current conclusion and evidence separately, plus machine reason and user decision/history.

### Compare Runs

Three primary views:
- new;
- changed;
- disappeared/not rediscovered.

Must not imply that a company ceased to exist merely because a provider did not return it.

## 10. Persistence invariants

1. A completed run is reproducible as a historical record even if the mission is edited later.
2. User notes/decisions are never silently overwritten by rerun.
3. Candidate history survives provider ordering changes where entity identity can be resolved.
4. Evidence retains run provenance.
5. Cross-tenant reads/writes are denied.
6. DB migrations are explicit and tested.
7. Backup/restore preserves user-visible state and audit linkage.
8. Admin policy changes affect future behavior according to policy semantics and do not rewrite historical evidence.
9. Dialogue changes create versioned Mission Brief revisions.
10. Preset, guided and constructor modes resolve to the same canonical configuration model.
11. Switching interaction level never loses mission state, evidence or provenance.
12. Professional recipes cannot override security/budget/authorization policy.

## 11. Quality acceptance model

Search quality alone is insufficient. Product acceptance measures four layers.

### Research quality
- qualified yield;
- direct/official yield;
- discovery novelty where applicable;
- waste;
- provenance completeness.

### Workflow quality
- task completion rate;
- time to first useful shortlist;
- number of user corrections required;
- clarification success rate;
- rerun success;
- delta correctness.

### Persistence quality
- saved state survives restart/relogin;
- edits survive rerun;
- historical run remains immutable;
- negative authorization passes;
- dialogue/brief/configuration provenance survives mode switching.

### Usability quality
- novice can complete a preset service without understanding search mechanics;
- guided user can refine content/form/depth without rebuilding a mission;
- professional user can build and reuse a recipe without bypassing governance;
- a representative user can explain what to do next from the interface itself.

## 12. Commercial readiness sequence

The dependency order is normative for this productization mission:

```text
pain validation
 -> business-process fit
 -> product state/business logic
 -> three-level UX + conversational loop
 -> quality acceptance
 -> durable DB + admin + tenancy
 -> billing/entitlements
 -> end-to-end commercial acceptance
 -> marketing and sales acquisition
```

Marketing is not used to conceal unfinished product state.

## 13. Open validation questions

These must be answered by observation/interviews/tests, not by architecture alone:

1. Who experiences the strongest pain: owner, head of sales, marketer, analyst, salesperson, procurement/research specialist?
2. Which exact event triggers a mission?
3. What is the current manual time/cost per mission?
4. Is the main value a broad universe, a qualified shortlist, fresh changes, or evidence-backed confidence?
5. How often must research be rerun?
6. What manual fields/notes are indispensable?
7. Which export/handoff destination matters first: XLSX/CSV, CRM, email/report, API?
8. Is a mission primarily individual or collaborative?
9. What candidate identity fields are necessary to reliably compare reruns?
10. What error is more expensive for the target user: missing a good company or including a bad one?
11. Which customer jobs deserve a one-click preset first?
12. Which controls belong in Guided mode and which should remain Professional-only?

The last two questions determine the first sellable service catalog and progression path.

## 14. Immediate engineering backlog derived from this blueprint

### PRODUCT-01B / #662
Translate this process into wireflow/UI contracts and persistence schema/backlog, including Preset / Guided / Professional modes.

### PRODUCT-01C / #663
Define representative acceptance scenarios and measurable pass/fail thresholds for the complete product workflow and all three interaction levels.

### PRODUCT-01D / #664
Implement durable product state, tenancy and admin control plane after the UX/state contracts stabilize.

### PRODUCT-01E / #665
Attach billing and entitlements only to the accepted product state and usage ledger.

### PRODUCT-01F / #666
Start marketing readiness only when the end-to-end user and payment paths are accepted.

## 15. Current boundary

The existing Hunter search technology is a strong execution engine, not yet the complete sellable product. Search research work remains valuable, but productization priority is now the durable customer workflow around that engine, exposed through a three-level progressive interaction architecture.