# Conversational Research Loop v0.1

**Status:** product interaction contract  
**Date:** 2026-08-15  
**Parent:** #660  
**UX/persistence:** #662

## Purpose

Hunter must not assume that a customer can fully specify a research task before the first search. The product must help the customer clarify, refine and deepen the task through dialogue with an AI consultant connected to the search/analytical engine until the result is satisfactory by **content, form and depth**.

This is a first-class business-process loop, not an optional chat widget.

## Core loop

```text
initial user need
  -> AI consultant clarification
  -> versioned Mission Brief
  -> agreed success criteria
  -> agreed output form
  -> agreed research depth
  -> search / analysis iteration
  -> intermediate result + evidence + gaps
  -> AI explanation and questions
  -> user feedback / correction / deepening
  -> explicit brief/scope/depth revision
  -> next search / analysis iteration
  -> ...
  -> user accepts result as sufficient
  -> saved working result + provenance + history
```

## What the AI consultant clarifies

The consultant may clarify when it materially improves execution:

- business goal and intended use of the result;
- target entities and exclusions;
- geography, industry and time boundaries;
- what constitutes a useful/qualified candidate;
- whether false positives or missed candidates are more costly;
- preferred search intent: Auto / Крупная рыба / Баланс / Золотой песок;
- desired output form;
- desired research depth;
- evidence expectations;
- whether the user wants breadth, confidence, novelty or completeness;
- constraints that conflict or are underspecified.

Clarification must be purposeful. The product should not interrogate the user for information that can safely be inferred, measured or resolved by the engine itself.

## Three independent dimensions of convergence

### 1. Content

What information the result must contain:
- which companies/entities;
- which facts and qualification attributes;
- which evidence;
- which comparisons or conclusions;
- which exclusions or uncertainty notes.

### 2. Form

How the customer needs the result delivered:
- candidate list;
- ranked shortlist;
- company cards;
- table;
- analytical note/report;
- comparison/delta;
- export/handoff package;
- combinations of the above.

The output form is part of the mission contract and may be revised through dialogue.

### 3. Depth

How far the system should investigate before stopping. Product naming may evolve, but the underlying contract must distinguish at least:

- **Quick scan** — rapid orientation and strong obvious candidates;
- **Working research** — evidence-backed operational result suitable for use;
- **Deep reconnaissance** — additional waves, rare findings, gap closure and deeper evidence where justified.

Research depth is not identical to search intent. For example, «Крупная рыба» can be run as a quick scan or as deep verification of a narrow high-value shortlist.

## Roles

### Customer / user

Owns the business objective and decides whether the result is useful enough.

### AI consultant

Acts as the cognitive interaction layer:
- understands the user's natural-language need;
- detects ambiguity and missing decision criteria;
- maintains an explicit Mission Brief;
- explains intermediate findings and gaps;
- translates user feedback into proposed mission changes;
- helps converge on an accepted result.

The AI consultant is **not** the execution authority for provider calls.

### Search / analytical engine

Executes the formalized mission under SearchGateway/provider/budget/policy controls and returns evidence, candidates, metrics and gap observations.

## Mission Brief as durable state

The current mission must be represented explicitly rather than hidden in chat context.

A Mission Brief revision should retain at least:
- business objective;
- target scope;
- inclusion/exclusion criteria;
- requested search intent;
- success criteria;
- output contract;
- research depth;
- evidence expectations;
- accepted constraints;
- revision actor/time/reason.

Each Search Run references the exact brief revision used for execution.

## Dialogue persistence

Mission-relevant conversation is durable product state.

Minimum entities:
- `consultation_thread`;
- `dialogue_turn`;
- `mission_brief_revision`;
- `clarification_proposal`;
- `scope_change`;
- `success_criteria`;
- `output_contract`;
- `research_depth_policy`.

The user must be able to return later and resume the conversation from the preserved business/research context.

## Material scope changes

A conversational request may change only presentation, or it may materially alter execution.

Examples of material change:
- add another region/country;
- broaden industry universe;
- switch from shortlist to exhaustive/discovery search;
- request a deeper evidence pass;
- add expensive provider/tool usage;
- rerun all candidates under new criteria.

When the change materially affects time/cost/scope, the AI consultant must present a concise proposed change before execution. This is not intended to add friction to harmless clarifications.

## Intermediate result checkpoint

After a search/analysis iteration the system should not merely display rows. It should be able to summarize:

- what was found;
- what evidence is strong;
- where evidence is weak or contradictory;
- which declared criteria remain unmet;
- which gaps were detected;
- what additional search/refinement could plausibly improve the result;
- what is unlikely to improve with more search;
- expected scope/cost of a material next iteration.

The user can then accept, refine, deepen, narrow, broaden or change the output form.

## Stop condition

The research loop should stop because the **customer's success condition is satisfied**, not merely because the first search wave ended.

Possible stop signals:
- user explicitly accepts the result;
- agreed shortlist size/quality/evidence criteria are met and user accepts;
- additional search has low expected marginal value and the user accepts current uncertainty;
- budget/depth limit is reached and the limitation is made explicit.

The system must not silently equate provider exhaustion with business-task completion.

## UX implications

The Mission Workspace should combine three synchronized surfaces:

1. **Conversation / AI consultant** — natural-language interaction and explanation;
2. **Mission Brief** — explicit current formal task, form, depth and criteria;
3. **Research result workspace** — candidates, evidence, shortlist, filters and deltas.

A useful pattern is that dialogue changes produce a visible proposed Brief diff rather than silently rewriting filters/settings behind the user's back.

## Business-logic invariants

1. Chat context alone is never the only source of mission state.
2. Material mission changes are versioned and attributable.
3. Search runs are tied to immutable mission snapshots.
4. Historical evidence remains interpretable after the mission evolves.
5. User decisions/notes are not overwritten by later AI iterations.
6. AI consultant cannot bypass SearchGateway, admin quality policy, entitlements or spend controls.
7. Result-form changes that do not require new research should reuse retained evidence where possible.
8. The system should prefer zero-cost re-analysis of retained evidence before new provider calls when the user changes only interpretation/presentation.
9. Conversation must survive logout/restart under the same tenant/authorization rules as other saved product state.
10. Provenance must explain how the final result evolved from the initial request.

## Product-quality metrics

In addition to search metrics, acceptance should measure:

- conversion of vague requests into executable Mission Briefs;
- clarification success rate;
- unnecessary-question rate;
- number of dialogue/search iterations to accepted result;
- content-fit acceptance;
- output-form acceptance;
- research-depth acceptance;
- user corrections needed after AI clarification;
- ability to explain scope evolution;
- context recovery after logout/restart;
- incremental time/cost of clarification versus measured quality gain;
- share of revisions satisfied by retained-evidence re-analysis rather than new search.

## Relationship to adaptive search

The conversational loop and the machine adaptive-search loop are complementary:

- machine gap detection proposes technical refinement based on evidence;
- AI consultant translates relevant gaps into user-understandable choices when business intent is ambiguous;
- user feedback supplies business semantics that telemetry alone cannot know;
- SearchGateway remains the governed execution boundary.

Therefore the desired architecture is not `chat OR search`, but:

```text
customer
  <-> AI consultant / mission cognition
        <-> versioned Mission Brief
              <-> governed search + analytical engine
                    <-> evidence / gaps / results
```

## Acceptance scenario

A representative user starts with: «Найди мне перспективных клиентов для нашего оборудования в Сибири».

The product should be able to discover through concise dialogue what «перспективный» means, which equipment/use cases matter, which regions count as Siberia for this mission, what evidence is necessary, whether the desired output is a broad universe or 30 strongest targets, and whether the user wants a quick scan or deeper reconnaissance.

After the first result the user may say: «Слишком много дилеров; мне нужны конечные промышленные предприятия. И покажи только те, где есть признаки модернизации производства».

AIMETON should turn that feedback into a visible new Brief revision, reuse retained evidence where possible, run only justified additional research, and preserve the full path from the original request to the accepted final shortlist.

## Current implementation boundary

This document defines product behavior and persistence requirements. It does not by itself authorize active adaptive second-wave execution, paid-provider escalation or silent scope changes. Those remain governed by existing search-quality, resource and entitlement controls.
