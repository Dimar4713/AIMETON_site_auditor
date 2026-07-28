#!/usr/bin/env python3
"""Compatibility entrypoint retained for the Project Status Sync workflow."""
from __future__ import annotations

import project_status_sync as sync


if __name__ == "__main__":
    try:
        raise SystemExit(sync.main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project status sync failed: {exc}", file=sync.sys.stderr)
        raise SystemExit(1)
