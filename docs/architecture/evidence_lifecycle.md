# Evidence lifecycle

## States

```text
discovery_hint
    ↓ explicit selection / qualification
source_candidate
    ↓ successful primary-document fetch + traceable quote
evidence
```

## Allowed transitions

- `discovery_hint → source_candidate`: URL selected for verification.
- `source_candidate → evidence`: the primary document was loaded successfully and the record contains document URL, title, access time and a quote from that document.
- `discovery_hint → evidence`: allowed only when the same operation both selects and successfully loads the primary document; all evidence fields are still mandatory.

## Forbidden transitions

- A search snippet cannot become evidence by classification, domain reputation, scoring or LLM interpretation alone.
- A failed document load cannot change lifecycle state or evidence strength.
- `query_kind`, `result_kind` and `source_class` cannot promote lifecycle state.

## Strength policy

- `discovery_hint` and `source_candidate` always use `unverified_mention`.
- Evidence strength is assigned only after document verification.
- Every evidence record must resolve to `document_url`, `document_accessed_at` and `evidence_quote`.

## Completeness

A company-intelligence result remains `partial` while it contains only hints or candidates. The `complete` state requires a deep site analysis and at least one verified evidence record.
