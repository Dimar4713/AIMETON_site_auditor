from __future__ import annotations

from copy import deepcopy
from threading import RLock

from app.sufficiency_evaluator.models import SufficiencyTurnRecord


class SufficiencyTraceStore:
    """Thread-safe in-process trace store aligned with the current in-memory mission runtime."""

    def __init__(self) -> None:
        self._records: dict[str, list[SufficiencyTurnRecord]] = {}
        self._lock = RLock()

    def append(self, record: SufficiencyTurnRecord) -> SufficiencyTurnRecord:
        with self._lock:
            records = self._records.setdefault(record.mission_id, [])
            expected_turn = len(records) + 1
            if record.turn_number != expected_turn:
                raise ValueError(
                    f"sufficiency turn must be sequential: expected {expected_turn}, "
                    f"got {record.turn_number}"
                )
            records.append(deepcopy(record))
            return deepcopy(record)

    def list_for_mission(self, mission_id: str) -> list[SufficiencyTurnRecord]:
        with self._lock:
            return deepcopy(self._records.get(mission_id, []))

    def latest(self, mission_id: str) -> SufficiencyTurnRecord | None:
        records = self.list_for_mission(mission_id)
        return records[-1] if records else None


_TRACE_STORE = SufficiencyTraceStore()


def get_sufficiency_trace_store() -> SufficiencyTraceStore:
    return _TRACE_STORE


def reset_sufficiency_trace_store() -> None:
    global _TRACE_STORE
    _TRACE_STORE = SufficiencyTraceStore()
