# Site Auditor burst parallel acceptance

Tracking: #783 and `Dimar4713/aimeton-infrastructure#329`.

This slice proves that the two prepared Site Auditor burst identities provide real parallel capacity after the shared seven-slot host allocation has been activated.

Acceptance is provider/model-free and exact-main pinned. The owner-only command on #783 is:

`/accept-burst-parallel-stage <site-auditor-main-sha>`

The dispatched workflow starts two jobs with labels `self-hosted,Linux,X64,stage,auditor,burst` and requires:

- two successful jobs;
- two distinct `aimeton-auditor-burst-stage-*` runner identities;
- actual overlap of the two execution intervals;
- no release authority and no hard-gate override.

This workflow is an acceptance measurement only. It does not wake/shelve infrastructure, register runners, perform model calls, or authorize Site Auditor as a production autoscaling input. Infrastructure cleanup and shelving are handled separately after terminal acceptance evidence.
