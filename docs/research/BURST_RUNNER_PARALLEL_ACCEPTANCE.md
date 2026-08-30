# Site Auditor burst parallel acceptance

Tracking: #783 and `Dimar4713/aimeton-infrastructure#329`.

This slice proves that the two prepared Site Auditor burst identities provide real parallel capacity after the shared seven-slot host allocation has been activated.

Acceptance is provider/model-free and exact-main pinned. The existing canonical owner-only AIMETON command router handles the command on #783:

`/accept-burst-parallel-stage <site-auditor-main-sha>`

No additional `issue_comment` workflow subscriber is introduced. The canonical router validates the owner, command syntax, issue binding and commit existence, then dispatches `burst-runner-parallel-acceptance.yml`. The acceptance workflow itself requires the requested SHA to equal current `main` before running the measurement.

The dispatched workflow starts two jobs with labels `self-hosted,Linux,X64,stage,auditor,burst`. GitHub scheduler placement is the label authority. Each job validates the generated projection against current canonical inventory in `aimeton-infrastructure`, then the runtime verifier proves physical identity, repository/source binding and contract membership with `source=burst`. The final check derives the complete accepted burst identity set from that validated projection. The workflow requires:

- two successful jobs;
- the two distinct burst identities declared by the `site-auditor-stage` contract;
- actual overlap of the two execution intervals;
- no release authority and no hard-gate override.

This workflow is an acceptance measurement only. It does not wake/shelve infrastructure, register runners, perform model calls, or authorize Site Auditor as a production autoscaling input. Infrastructure cleanup and shelving are handled separately after terminal acceptance evidence.
