# Command router slice 1 verification

- router is the only command parser for the migrated commands;
- checkpoint acceptance is workflow-dispatch only;
- mobile UI acceptance is workflow-dispatch only;
- exact SHA input is required;
- command-specific issue allowlists are preserved;
- unknown commands dispatch nothing;
- deploy and repair workflows are unchanged;
- stage and evidence gates are unchanged.
