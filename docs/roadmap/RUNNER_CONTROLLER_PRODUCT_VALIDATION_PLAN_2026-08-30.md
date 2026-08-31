# Runner Controller product validation plan

Status: implementation correction in progress  
Recorded: `2026-08-31T11:13:33Z`  
Scope: provider-free Site Auditor acceptance only

## Traceability

- Infrastructure implementation: `Dimar4713/aimeton-infrastructure#567`, merged as `1270bab9161f7b90c426c55445f3b19800e6ce51`.
- Infrastructure lifecycle: `Dimar4713/aimeton-infrastructure#240` and `#329`.
- Product implementation: #854; supersedes closed draft #851.

## Implemented product slice

1. The independent pilot inventory and resolver are absent.
2. The generated projection records canonical repository, exact infrastructure source SHA, three source paths, immutable Git blob IDs and payload SHA-256.
3. Runtime verification fails closed on unknown identity, wrong repository/source, duplicate key/name, selector incompatibility and missing/stale expected projection digest.
4. The existing parallel acceptance derives both burst identities from the projection; no runner-name regex is identity authority.
5. GitHub scheduler owns label placement. Runtime labels are verified only when an explicit trusted signal is available.

## Cross-repository correction

The first implementation called a reusable workflow in private `aimeton-infrastructure` from public Site Auditor. Run `33317877557` failed before creating any job, so this was a workflow accessibility failure, not a runner shortage.

The product now validates immutable projection integrity on `ubuntu-latest` without private credentials. Canonical freshness and synchronization are executed from the existing trusted infrastructure control-plane/server path using the central credential contract. Product runtime evidence explicitly reports that it verifies projection integrity and identity membership, not live canonical freshness.

## Remaining acceptance

- merge #854 only after provider-free CI is terminal GREEN and the canonical-side sync/drift slice is reviewable;
- perform exactly one owner-authorized lifecycle acceptance after merged exact-main prerequisites;
- measure `queue_created_at → runner_job_started_at`, distinct identities, overlap, drain, cooldown and shelve/read-back;
- do not claim queue-delay removal or lifecycle completion before terminal live evidence.
