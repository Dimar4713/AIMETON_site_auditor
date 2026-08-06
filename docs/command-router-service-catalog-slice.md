# Command router service catalog slice

- Command: `/accept-service-catalog-stage <sha>`
- Allowed issue: `#274`
- Target workflow: `accept-service-catalog-stage.yml`
- Input: `expected_sha`
- Downstream trigger: `workflow_dispatch` only
- Exact SHA, stage health, evidence publication and safety checks remain unchanged.
