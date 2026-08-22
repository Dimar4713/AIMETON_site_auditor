# ACCB immutable execution snapshot

Source of truth: `Dimar4713/aimeton-architecture` commit `db18fcbc0a50d96af4e747db0ec2df10ca79f64c`.

This directory exists only to let the Site Auditor execution plane run the ACCB RouterAI calibration without granting its repository-scoped GitHub Actions token cross-repository read access. `SNAPSHOT_MANIFEST.json` records canonical Git blob SHAs. The live workflow verifies every blob with `git hash-object` before any RouterAI request is admitted.

The snapshot does not become an independent source of architectural truth. Any future ACCB revision must originate in `aimeton-architecture`, receive a new pinned source commit, and be revendored with a new manifest.
