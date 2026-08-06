# MCP runtime.time acceptance

The live acceptance workflow calls the public stage MCP Streamable HTTP endpoint and verifies the `runtime.time` tool without installing third-party packages at runtime.

Acceptance gates:

- MCP initialize succeeds and returns a session identifier;
- `tools/list` exposes `runtime.time`;
- `tools/call` returns `source=chrony` and `synced=true`;
- quality is `trusted`;
- absolute offset is at most 50 ms;
- stratum is at most 4;
- evidence contains no secret values.
