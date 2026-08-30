# Runner Controller product validation plan

Status: implementation started  
Recorded: `2026-08-30T13:19:44Z`  
Scope: provider-free Site Auditor acceptance only

## Traceability

- Architecture: `Dimar4713/aimeton-architecture#128`.
- Infrastructure lifecycle: `Dimar4713/aimeton-infrastructure#240` and `#329`.
- Infrastructure inventory: `Dimar4713/aimeton-infrastructure#353`.
- Existing product acceptance: `burst-runner-parallel-acceptance.yml`.

## Observed gap

The product workflow selects the burst capability by labels, but runtime identity validation was a hardcoded runner-name regular expression. It could neither consume an inventory nor prove that the selected identity belongs to the contract-resolved pool.

## Bounded implementation slice

1. Generate the Site Auditor stage projection from canonical persistent/burst inventory in `aimeton-infrastructure`.
2. Record exact infrastructure source SHA, source paths and Git blob digests, and fail closed when current canonical blobs or projected runner fields drift.
3. Fail closed at runtime when the executing identity is outside the resolved pool.
4. Make the existing two-slot burst acceptance require a `burst` source from that contract.
5. Keep provider actions, runner registration, topology changes, production workflow changes and merge authority outside this slice.

## Acceptance

- provider-free tests accept both declared burst identities;
- the persistent runner remains eligible for the stage contract but is rejected by burst-only acceptance;
- an unknown, duplicate, cross-repository or selector-incompatible identity fails closed;
- the live acceptance workflow derives accepted names from contract output rather than a name prefix;
- two distinct runners and real execution overlap remain mandatory.

Live queue-delay removal is not claimed until the owner-authorized acceptance workflow runs against current `main` and records terminal evidence.

## Canonical inventory boundary

The independent pilot inventory and resolver were removed on `2026-08-30T13:46:34Z`. The generated projection is not a second source of truth. Because both repositories are private and cross-repository credentials are forbidden, validation uses the canonical reusable workflow in `aimeton-infrastructure/main`: it renders the projection from persistent inventory, Site Auditor burst inventory and repository-pool policy, then returns a SHA-256 proof. Product PR validation and live acceptance fail closed when that proof differs from the generated artifact. The runtime verifier requires the same proof before accepting an identity.

GitHub `runs-on` remains the authority for capability labels. Runtime verification proves physical identity, repository/source binding and contract membership. It reports `runtime_labels_verified=false` when a reliable label signal is unavailable rather than claiming an unperformed check.
