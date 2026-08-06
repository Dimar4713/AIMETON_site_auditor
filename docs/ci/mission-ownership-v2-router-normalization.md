# Mission ownership V2 router normalization

`stage-mission-ownership-acceptance-v2.yml` is the canonical disruptive ownership and persistence acceptance workflow for Issue #177.

Its command contract is normalized to `/accept-mission-stage-v2 <40-char SHA>` through the single AIMETON command router. The workflow now requires `workflow_dispatch.expected_sha` and verifies the deployed source SHA before creating temporary identities or mission records. Its container restart, compose force-recreate, cleanup, isolation, persistence, integrity and sanitized evidence assertions remain unchanged.
