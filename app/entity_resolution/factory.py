from __future__ import annotations

from app.entity_resolution.service import ProvisionalEntityResolver


_resolver: ProvisionalEntityResolver | None = None


def get_entity_resolver() -> ProvisionalEntityResolver:
    global _resolver
    if _resolver is None:
        _resolver = ProvisionalEntityResolver()
    return _resolver


def reset_entity_resolver() -> None:
    global _resolver
    _resolver = None
