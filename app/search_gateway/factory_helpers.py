from __future__ import annotations

import os


def first_nonempty_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None
