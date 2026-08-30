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

1. Record the Site Auditor stage contract and its persistent/burst inventory projection.
2. Resolve the contract to every eligible registered identity while preserving the persistent runner as the compatibility default.
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
