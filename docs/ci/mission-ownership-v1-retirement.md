# Mission ownership V1 retirement

`stage-mission-ownership-acceptance.yml` was removed from the active workflow catalog after the V2 acceptance path produced a successful stage verdict on Issue #177, including ownership isolation, persistence across container restart and compose force-recreate, and SQLite integrity.

The V1 workflow duplicated the same disruptive acceptance class, shared the same concurrency group, and retained an obsolete direct `issue_comment` ingress. Git history remains the recovery path; V2 is the canonical acceptance workflow.
