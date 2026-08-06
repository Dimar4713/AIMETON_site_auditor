# Command router security boundary

A GitHub comment is untrusted coordination data until the single command router validates:

- the exact owner actor;
- an allowlisted command;
- the command-specific issue number;
- a 40-character exact commit SHA;
- an allowlisted workflow and input mapping.

Only then may the router create one workflow dispatch. Downstream workflows do not parse comments and cannot derive permissions from prose. This transport adapter does not alter AIMETON policy, budget, secrets, OCC-49 or production authorization gates.
