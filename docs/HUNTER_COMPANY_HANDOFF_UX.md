# Hunter → Company Intelligence handoff UX

The selected Hunter candidate must remain unambiguous when transferred into Company Intelligence.

## Invariants

- Show an explicit **Selected candidate** context before the research form.
- Always show the selected domain and region when available.
- Mark the origin as **From client search**.
- Do not present a generic/category search title as a verified company or brand name.
- If a trustworthy exact name is not available, identify the object as **Company at <domain>**.
- Keep the original search-result title only as provenance/context, not verified identity.
- Do not auto-submit Company Intelligence after the handoff; the user explicitly launches research.
- Completion status should name the researched domain when available.
