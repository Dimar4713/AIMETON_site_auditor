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

```text
Workspace / Project
  -> create Research Mission
  -> define target + constraints + user search intent
  -> run Search Run v1
  -> observe progress
  -> inspect Candidate Companies + Evidence
  -> qualify / reject / defer
  -> add notes / manual overrides
  -> assemble Saved Shortlist
  -> export / hand off
  -> return later
  -> rerun as Search Run v2
  -> compare v2 vs v1
  -> review new / changed / disappeared candidates
  -> preserve old decisions and evidence
  -> update shortlist
```

### User-visible search intent

The user selects the goal, not technical coefficients:

- **Auto** — AIMETON chooses the tactic from observed state;
- **Крупная рыба** — prioritize the strongest/high-confidence candidates;
- **Баланс** — balance shortlist quality and breadth;
- **Золотой песок** — search deeper for rare or easy-to-miss candidates.

Technical thresholds remain administrator-owned policy.

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

### Search Run

Immutable execution/version of a mission.

Minimum fields:
- run id;
- mission id;
- parent/prior run id when rerun;
- mission snapshot;
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
- edit mission before run;
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
- rerun/update mission;
- compare runs;
- preserve manual decisions across reruns;
- archive/restore where applicable;
- export/handoff;
- return after logout/restart and recover the same state.

## 9. UX information architecture v0.1

### Dashboard

Shows active projects/missions, status, last run, saved shortlist count and next useful action.

### New Mission Wizard

Steps:
1. business target;
2. geography;
3. include/exclude criteria;
4. search intent;
5. review expected scope/cost boundary;
6. launch.

### Mission Workspace

Persistent screen with tabs/sections:
- Overview;
- Runs;
- Candidates;
- Shortlists;
- Notes/Activity;
- Exports.

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
- rerun success;
- delta correctness.

### Persistence quality
- saved state survives restart/relogin;
- edits survive rerun;
- historical run remains immutable;
- negative authorization passes.

### Usability quality
A representative user can complete the core path without developer assistance and can explain what to do next from the interface itself.

## 12. Commercial readiness sequence

The dependency order is normative for this productization mission:

```text
pain validation
 -> business-process fit
 -> product state/business logic
 -> UX workspace
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

The last question directly determines whether «Крупная рыба» or «Золотой песок» should be the default for a particular workflow.

## 14. Immediate engineering backlog derived from this blueprint

### PRODUCT-01B / #662
Translate this process into wireflow/UI contracts and persistence schema/backlog.

### PRODUCT-01C / #663
Define representative acceptance scenarios and measurable pass/fail thresholds for the complete product workflow.

### PRODUCT-01D / #664
Implement durable product state, tenancy and admin control plane after the UX/state contracts stabilize.

### PRODUCT-01E / #665
Attach billing and entitlements only to the accepted product state and usage ledger.

### PRODUCT-01F / #666
Start marketing readiness only when the end-to-end user and payment paths are accepted.

## 15. Current boundary

The existing Hunter search technology is a strong execution engine, not yet the complete sellable product. Search research work remains valuable, but productization priority is now the durable customer workflow around that engine.
