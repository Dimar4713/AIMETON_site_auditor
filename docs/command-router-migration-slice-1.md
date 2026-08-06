# AIMETON Command Router — migration slice 1

## Migrated commands

| Command | Issue | Workflow | Input |
|---|---:|---|---|
| `/accept-checkpoint-stage <sha>` | 88 | `accept-checkpoint-stage.yml` | `expected_sha` |
| `/accept-mobile-ui-stage <sha>` | 223 | `accept-mobile-ui-stage.yml` | `expected_sha` |

## Contract

- `aimeton-command-router.yml` is the only `issue_comment` ingress for these commands.
- The router authenticates the owner actor, validates the exact command, exact issue and 40-character commit SHA.
- Downstream workflows accept only `workflow_dispatch` with `expected_sha`.
- Existing self-hosted runner, stage environment, exact deployed SHA and evidence publication gates remain unchanged.
- Unknown slash commands create no downstream dispatch.

## Fan-out effect

For an ordinary comment, these two downstream workflows no longer create separate mostly-skipped workflow runs.
