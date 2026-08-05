from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class TraceIdentity:
    mission_id: str
    attempt_id: str


_TRACE_IDENTITY: ContextVar[TraceIdentity | None] = ContextVar(
    "aimeton_trace_identity",
    default=None,
)


def current_trace_identity() -> TraceIdentity | None:
    """Return the mission identity bound to the current async execution context."""
    return _TRACE_IDENTITY.get()


@contextmanager
def bind_trace_identity(mission_id: str, attempt_id: str) -> Iterator[TraceIdentity]:
    """Bind user-visible mission identity through nested async provider calls."""
    identity = TraceIdentity(mission_id=mission_id, attempt_id=attempt_id)
    token = _TRACE_IDENTITY.set(identity)
    try:
        yield identity
    finally:
        _TRACE_IDENTITY.reset(token)
