# Exact-SHA stage deployment gate

A successful `Baseline CI` run on `main` must lead to a real stage deployment of the same 40-character commit SHA.

A `Deploy Stage` workflow where the `deploy` job is skipped is not deployment evidence and must not trigger live acceptance.

Required invariants:

- no PyPI or runtime dependency installation during deploy;
- OpenStack SDK is not a deployment prerequisite;
- checkout SHA equals requested SHA;
- transactional switch, health verification and sanitized evidence remain mandatory;
- live MCP acceptance runs only against the actually deployed bundle SHA.

This contract closes the false-success path where a workflow-only merge left stage on an older application bundle.
