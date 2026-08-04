# AIMETON agent execution instructions

Canonical source: `Dimar4713/aimeton-architecture/docs/operations/AGENT_GITHUB_EXECUTION_BRIDGE.md`.

## Mandatory operating loop

1. Start every progress message with a real timestamp.
2. Read the durable handoff and current Issue, PR, CI, artifact and stage evidence.
3. Keep a three-step queue: active task, next task, next-after-next.
4. Perform the next safe and agreed action immediately; do not write “continuing” and then stop.
5. Stop only at a genuine blocker requiring owner judgement or authority.

## GitHub capability escalation

Before asking the owner for manual GitHub actions, exhaust these channels:

1. built-in GitHub connector/API;
2. AIMETON GitHub MCP;
3. trusted REST/GraphQL/`gh` server path;
4. approved repository-native indirect command bridge.

When a direct `workflow_dispatch` is unavailable, use an owner-only `issue_comment` command bridge that:

- accepts commands only in an allow-listed control Issue;
- accepts only the owner or an explicit actor allow-list;
- uses strict command grammar and exact 40-character SHA when applicable;
- verifies the commit exists;
- fails closed on actor, Issue, command or SHA mismatch;
- invokes the existing authoritative workflow rather than duplicating execution logic;
- keeps token permissions minimal and does not add write access merely for acknowledgement;
- verifies workflow, artifact, exact SHA and runtime/stage read-back before claiming success.

## Site Auditor control plane

Canonical durable handoff: Issue #173.

Proven commands include:

- `/deploy-stage <sha>`;
- `/accept-mobile-ui-stage <sha>`;
- `/accept-service-catalog-stage <sha>`;
- `/accept-ui-stage <sha>`.

## Safety

Never expose secrets, credentials, prompts, chain-of-thought, provider payloads or internal paths. Do not create costs or perform unapproved production, budget, legal, OCC-49 or architecture-invariant changes.
