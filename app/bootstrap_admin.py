from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.admin_users import AdminSQLiteUserRepository
from app.auth import bootstrap_admin_from_env


def bootstrap(database: str | Path) -> tuple[str, int]:
    repository = AdminSQLiteUserRepository(database)
    user = bootstrap_admin_from_env(repository)
    if user is None:
        raise RuntimeError("bootstrap admin secrets are not configured")
    return user.username, user.id


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotently bootstrap the first AIMETON admin from environment secrets.")
    parser.add_argument("--database", default=os.getenv("AIMETON_AUTH_DB", "data/auth.sqlite3"))
    args = parser.parse_args()
    path = Path(args.database)
    path.parent.mkdir(parents=True, exist_ok=True)
    username, user_id = bootstrap(path)
    print(f"bootstrap_admin=ok username={username} user_id={user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
