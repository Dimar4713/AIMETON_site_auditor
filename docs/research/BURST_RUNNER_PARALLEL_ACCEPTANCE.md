# Site Auditor burst parallel acceptance

Tracking: #783 and `Dimar4713/aimeton-infrastructure#329`.

This slice proves that the two prepared Site Auditor burst identities provide real parallel capacity after the shared host allocation has been activated.

Acceptance is provider/model-free and exact-main pinned. The existing owner-only command router dispatches `burst-runner-parallel-acceptance.yml` from #783.

GitHub scheduler `runs-on` labels are capability-placement authority. Each runtime job validates the immutable generated projection digest and proves physical identity membership, repository ownership and `source=burst`. It does not claim runtime label verification unless a trusted label signal is explicitly supplied. The final job derives the complete burst identity set from the projection and requires:

- two successful jobs;
- exactly the two projected burst identities;
- actual overlap of execution intervals;
- no provider/model call, release authority or hard-gate override.

The public product workflow does not call the private infrastructure repository. The trusted infrastructure control plane publishes the canonical generated document to the machine-owned same-repository branch `aimeton-control/runner-projection-sync`. Product CI and live acceptance fetch that branch with the ordinary read-only Site Auditor token and fail closed unless its document exactly equals the PR/main artifact. The document records exact infrastructure SHA, source paths, blob IDs and payload digest. No privileged credential is copied into Site Auditor workflows.

This workflow is an acceptance measurement only. It does not wake/shelve infrastructure, register runners or activate autoscaling.
