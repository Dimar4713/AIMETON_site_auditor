from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


UMEL_VERSION = "1.0.0"


class UmelSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    ACTION_REQUIRED = "action_required"


class UmelEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    icon: str
    label_ru: str
    label_en: str
    severity: UmelSeverity
    terminal: bool = False


_EVENTS = (
    UmelEvent(code="mission.received", icon="🧭", label_ru="Миссия получена", label_en="Mission received", severity=UmelSeverity.INFO),
    UmelEvent(code="goal.resolved", icon="🎯", label_ru="Цель определена", label_en="Goal resolved", severity=UmelSeverity.INFO),
    UmelEvent(code="route.planned", icon="🗺️", label_ru="Маршрут построен", label_en="Route planned", severity=UmelSeverity.INFO),
    UmelEvent(code="research.started", icon="🔎", label_ru="Исследование начато", label_en="Research started", severity=UmelSeverity.INFO),
    UmelEvent(code="provider.requested", icon="🌐", label_ru="Запрос к источнику", label_en="Provider requested", severity=UmelSeverity.INFO),
    UmelEvent(code="provider.responded", icon="📡", label_ru="Источник ответил", label_en="Provider responded", severity=UmelSeverity.INFO),
    UmelEvent(code="data.received", icon="📦", label_ru="Данные получены", label_en="Data received", severity=UmelSeverity.INFO),
    UmelEvent(code="data.integrated", icon="🔗", label_ru="Данные объединяются", label_en="Data integration", severity=UmelSeverity.INFO),
    UmelEvent(code="picture.assembled", icon="🧩", label_ru="Целостная картина собирается", label_en="Picture assembled", severity=UmelSeverity.INFO),
    UmelEvent(code="analysis.running", icon="🧠", label_ru="Анализ выполняется", label_en="Analysis running", severity=UmelSeverity.INFO),
    UmelEvent(code="evidence.checked", icon="⚖️", label_ru="Доказательства проверяются", label_en="Evidence checked", severity=UmelSeverity.INFO),
    UmelEvent(code="confidence.scored", icon="📊", label_ru="Уверенность оценена", label_en="Confidence scored", severity=UmelSeverity.INFO),
    UmelEvent(code="flow.gap_detected", icon="🚧", label_ru="Обнаружен разрыв потока", label_en="Flow gap detected", severity=UmelSeverity.WARNING),
    UmelEvent(code="repair.running", icon="🩹", label_ru="Исправление выполняется", label_en="Repair running", severity=UmelSeverity.WARNING),
    UmelEvent(code="attempt.retrying", icon="♻️", label_ru="Повторная попытка", label_en="Retrying", severity=UmelSeverity.WARNING),
    UmelEvent(code="external.waiting", icon="⏳", label_ru="Ожидание внешнего сервиса", label_en="Waiting for external service", severity=UmelSeverity.INFO),
    UmelEvent(code="service.degraded", icon="⚠️", label_ru="Сервис работает в деградированном режиме", label_en="Service degraded", severity=UmelSeverity.WARNING),
    UmelEvent(code="protection.active", icon="🛡️", label_ru="Защитный режим активен", label_en="Protection active", severity=UmelSeverity.WARNING),
    UmelEvent(code="critical_path.active", icon="🔥", label_ru="Критический путь активен", label_en="Critical path active", severity=UmelSeverity.INFO),
    UmelEvent(code="owner.decision_required", icon="👤", label_ru="Требуется решение владельца", label_en="Owner decision required", severity=UmelSeverity.ACTION_REQUIRED),
    UmelEvent(code="evidence.saved", icon="💾", label_ru="Доказательства сохранены", label_en="Evidence saved", severity=UmelSeverity.INFO),
    UmelEvent(code="journal.updated", icon="📜", label_ru="Журнал обновлён", label_en="Journal updated", severity=UmelSeverity.INFO),
    UmelEvent(code="stage.completed", icon="✅", label_ru="Этап завершён", label_en="Stage completed", severity=UmelSeverity.SUCCESS),
    UmelEvent(code="mission.failed", icon="❌", label_ru="Миссия завершилась ошибкой", label_en="Mission failed", severity=UmelSeverity.ERROR, terminal=True),
    UmelEvent(code="mission.completed", icon="🎉", label_ru="Миссия успешно завершена", label_en="Mission completed", severity=UmelSeverity.SUCCESS, terminal=True),
)

REGISTRY = {event.code: event for event in _EVENTS}


def list_umel_events() -> list[UmelEvent]:
    return list(_EVENTS)


def get_umel_event(code: str) -> UmelEvent | None:
    return REGISTRY.get(code)
