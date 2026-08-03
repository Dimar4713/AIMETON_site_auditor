from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _integrity_check(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise ValueError("runtime database integrity check failed")


def backup_runtime_database(source: str | Path, destination: str | Path) -> Path:
    """Create an atomic SQLite backup and verify it before publication."""
    source_path = Path(source)
    destination_path = Path(destination)
    _integrity_check(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(destination_path.name + ".tmp")
    temporary_path.unlink(missing_ok=True)

    try:
        with sqlite3.connect(source_path) as source_connection:
            with sqlite3.connect(temporary_path) as destination_connection:
                source_connection.backup(destination_connection)
        _integrity_check(temporary_path)
        os.replace(temporary_path, destination_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return destination_path


def restore_runtime_database(backup: str | Path, destination: str | Path) -> Path:
    """Restore a verified backup atomically without mutating the source backup."""
    backup_path = Path(backup)
    destination_path = Path(destination)
    _integrity_check(backup_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(destination_path.name + ".restore.tmp")
    temporary_path.unlink(missing_ok=True)

    try:
        with sqlite3.connect(backup_path) as backup_connection:
            with sqlite3.connect(temporary_path) as destination_connection:
                backup_connection.backup(destination_connection)
        _integrity_check(temporary_path)
        os.replace(temporary_path, destination_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return destination_path
