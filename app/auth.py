from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Protocol


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: UserRole
    is_active: bool


@dataclass(frozen=True)
class Session:
    token: str
    user_id: int
    expires_at: datetime


class UserRepository(Protocol):
    def create_user(self, username: str, password_hash: str, role: UserRole) -> User: ...

    def get_by_username(self, username: str) -> tuple[User, str] | None: ...

    def get_by_id(self, user_id: int) -> User | None: ...

    def set_active(self, user_id: int, active: bool) -> None: ...


class AuthProvider(Protocol):
    def authenticate(self, username: str, password: str) -> User | None: ...

    def create_session(self, user: User) -> Session: ...

    def resolve_session(self, token: str) -> User | None: ...

    def revoke_session(self, token: str) -> None: ...


class PasswordHasher:
    """Versioned scrypt password hashes using only Python's standard library."""

    algorithm = "scrypt"
    n = 2**14
    r = 8
    p = 1
    dklen = 64

    def hash(self, password: str) -> str:
        if len(password) < 12:
            raise ValueError("password must contain at least 12 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self.n,
            r=self.r,
            p=self.p,
            dklen=self.dklen,
        )
        return "$".join(
            [
                self.algorithm,
                str(self.n),
                str(self.r),
                str(self.p),
                salt.hex(),
                digest.hex(),
            ]
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$", 5)
            if algorithm != self.algorithm:
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(bytes.fromhex(digest_hex)),
            )
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(actual.hex(), digest_hex)


class SQLiteUserRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )

    def create_user(self, username: str, password_hash: str, role: UserRole) -> User:
        normalized = username.strip().lower()
        if not normalized or len(normalized) > 128:
            raise ValueError("invalid username")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (normalized, password_hash, role.value, datetime.now(UTC).isoformat()),
            )
            user_id = int(cursor.lastrowid)
        return User(user_id, normalized, role, True)

    def get_by_username(self, username: str) -> tuple[User, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        if row is None:
            return None
        return (
            User(row["id"], row["username"], UserRole(row["role"]), bool(row["is_active"])),
            row["password_hash"],
        )

    def get_by_id(self, user_id: int) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, role, is_active FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return User(row["id"], row["username"], UserRole(row["role"]), bool(row["is_active"]))

    def set_active(self, user_id: int, active: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if active else 0, user_id),
            )
            if not active:
                connection.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    (datetime.now(UTC).isoformat(), user_id),
                )

    def store_session(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at.isoformat()),
            )

    def resolve_session(self, token_hash: str, now: datetime) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, u.role, u.is_active, s.expires_at, s.revoked_at
                FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= now:
            return None
        if not bool(row["is_active"]):
            return None
        return User(row["id"], row["username"], UserRole(row["role"]), True)

    def revoke_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (datetime.now(UTC).isoformat(), token_hash),
            )


class LocalAuthProvider:
    def __init__(
        self,
        repository: SQLiteUserRepository,
        *,
        hasher: PasswordHasher | None = None,
        session_ttl: timedelta = timedelta(hours=12),
    ):
        self.repository = repository
        self.hasher = hasher or PasswordHasher()
        self.session_ttl = session_ttl

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def authenticate(self, username: str, password: str) -> User | None:
        record = self.repository.get_by_username(username)
        if record is None:
            return None
        user, password_hash = record
        if not user.is_active or not self.hasher.verify(password, password_hash):
            return None
        return user

    def create_session(self, user: User) -> Session:
        if not user.is_active:
            raise PermissionError("inactive user")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + self.session_ttl
        self.repository.store_session(self._token_hash(token), user.id, expires_at)
        return Session(token, user.id, expires_at)

    def resolve_session(self, token: str) -> User | None:
        if not token:
            return None
        return self.repository.resolve_session(self._token_hash(token), datetime.now(UTC))

    def revoke_session(self, token: str) -> None:
        if token:
            self.repository.revoke_session(self._token_hash(token))


def bootstrap_admin_from_env(
    repository: SQLiteUserRepository,
    *,
    username_env: str = "AIMETON_BOOTSTRAP_ADMIN_USERNAME",
    password_env: str = "AIMETON_BOOTSTRAP_ADMIN_PASSWORD",
) -> User | None:
    username = os.getenv(username_env, "").strip()
    password = os.getenv(password_env, "")
    if not username and not password:
        return None
    if not username or not password:
        raise RuntimeError("both bootstrap admin variables must be set")
    existing = repository.get_by_username(username)
    if existing is not None:
        return existing[0]
    password_hash = PasswordHasher().hash(password)
    return repository.create_user(username, password_hash, UserRole.ADMIN)
