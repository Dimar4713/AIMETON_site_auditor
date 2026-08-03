# SR-07 runtime checkpoint persistence boundary

Part of #88.

This slice persists sanitized `MissionCheckpoint` envelopes through the existing Runtime Core event store. It does not add a second storage system or mutate stage/production.

Acceptance evidence is provided by deterministic tests proving:

- a checkpoint survives closing and reopening `RuntimeStore`;
- replay of the same checkpoint writes no duplicate event;
- sequence rollback and same-sequence digest conflicts fail closed;
- payload contains only the typed checkpoint envelope and existing audit metadata.

Restart/redeploy stage acceptance and backup/restore remain subsequent gates.
