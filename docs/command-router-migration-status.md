# Command router migration status

## Completed in slice 1

- `accept-checkpoint-stage.yml` no longer subscribes directly to `issue_comment`.
- `accept-mobile-ui-stage.yml` no longer subscribes directly to `issue_comment`.
- Both commands are routed by `aimeton-command-router.yml` with exact issue and exact SHA validation.
- Existing stage runner, environment, exact deployment identity and evidence publication remain unchanged.

## Next safe slice

Migrate `accept-admin-trace-stage.yml` and `accept-aimeton-self-audit-stage.yml` after exact full-file read-back. Do not touch deploy or repair workflows in the same slice.
