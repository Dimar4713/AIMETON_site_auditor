# AIMETON Command Router route matrix

| Command | Allowed issue | Target workflow | Dispatch input | State |
|---|---:|---|---|---|
| `/deploy-stage <sha>` | 337 | `deploy-stage.yml` | `commit_sha` | routed, downstream migration pending |
| `/accept-admin-trace-stage <sha>` | 293 | `accept-admin-trace-stage.yml` | `expected_sha` | routed, downstream migration pending |
| `/accept-aimeton-self-audit-stage <sha>` | 293 | `accept-aimeton-self-audit-stage.yml` | `expected_sha` | routed, downstream migration pending |
| `/accept-checkpoint-stage <sha>` | 88 | `accept-checkpoint-stage.yml` | `expected_sha` | migrated |
| `/accept-mobile-ui-stage <sha>` | 223 | `accept-mobile-ui-stage.yml` | `expected_sha` | migrated |

Every routed command requires the owner actor, the exact allowed issue and a 40-character hexadecimal commit SHA. Unknown commands are ignored without downstream dispatch.
