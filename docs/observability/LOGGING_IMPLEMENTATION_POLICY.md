# AIMETON Site Auditor — Logging and Retention Implementation Policy

Статус: project contract. Основан на канонической политике `Dimar4713/aimeton-architecture/docs/governance/AIMETON_LOGGING_GOVERNANCE.md`.

## Цель

Обеспечить доказуемый сквозной технологический trace миссий и поискового data-flow, не раскрывая секреты и не ухудшая доступность приложения.

## 1. Всегда формируем все безопасные классы событий

Приложение формирует `emergency`, `operational`, `diagnostic`, `trace`, `forensic`. Настройка режима влияет на retention, aggregation, UI projection и стоимость записи, а не на смысловую модель уровней.

## 2. Обязательный поток миссии

`mission_created → execution_started → plan_built → provider_selected/skipped → request_started → response_received/failed → normalized → deduplicated → identity_checked → evidence_accepted/rejected → aggregated → vertical_completed/degraded → synthesis → report_gate → export_created`

Каждый переход получает typed `reason_code`, counters и duration. Для provider waterfall обязательно фиксируются `selected`, `called`, `state`, `reason`, `latency_ms`, `results_received`, `normalized`, `accepted`, `rejected`, `used_in_report`.

## 3. Хранилище и схема

Durable append-only ledger использует Runtime Core SQLite и общий persistent volume. Событие содержит:

- `event_id`, `event_key`, `mission_id`, `attempt_id`, sequence;
- UTC timestamp, component, operation, state, reason_code;
- provider/vertical при наличии;
- bounded counters и sanitized metadata;
- deployed SHA/runtime version;
- `retention_class`, `policy_version`, `retain_until`;
- `frozen`, `legal_hold`, `incident_id` при наличии.

Trace не является authoritative mission state.

## 4. Базовая retention policy

| Class | Minimum |
|---|---:|
| emergency | 365 days |
| operational | 180 days |
| diagnostic | 30 days |
| trace | 7 days |
| forensic | 24 hours |

Сокращение уже назначенного `retain_until` запрещено без отдельного owner decision. Увеличение может применяться к существующим событиям.

## 5. Retention Manager

Worker запускается:

- периодически;
- при старте приложения;
- после изменения policy;
- внеочередно при resource pressure.

Удаление только `expired-only`, batch-операциями. Исключаются активные, frozen, legal hold и связанные с открытым incident записи. Поддерживаются dry-run, reclaimed bytes и компактный audit outcome.

Порядок очистки при дефиците диска: expired forensic → trace → diagnostic → operational → emergency. Непросроченные записи автоматически не удаляются.

## 6. Ресурсные режимы

`FULL → THROTTLED → MINIMAL → EMERGENCY_ONLY → WRITE_DISABLED`

- `FULL`: полная безопасная запись;
- `THROTTLED`: batch/aggregation, сниженная sampling frequency, digest для oversized metadata;
- `MINIMAL`: terminal, errors, provider outcome, counters, resource state;
- `EMERGENCY_ONLY`: fatal/error/abort/storage и logging mode transitions;
- `WRITE_DISABLED`: основной ledger отключён, bounded preallocated ring buffer сохраняет минимальный аварийный след и dropped counters.

Observability работает fail-open: её сбой не должен ломать поиск, анализ или выдачу отчёта.

## 7. Автоматические переходы

Пороговые параметры конфигурируются. Минимальный набор сигналов:

- queue depth;
- write latency p95;
- disk free percent;
- memory/CPU pressure и OOM risk;
- SQLite busy/locked;
- logging worker failures;
- observability overhead ratio.

Обязательны hysteresis, cooldown и восстановление по одной ступени. Все переходы записываются отдельными typed events.

## 8. Ручное управление

Admin/owner API и UI должны поддерживать:

- status текущего режима и причины;
- `auto`, `full`, `throttled`, `minimal`, `emergency-only`, `write-disabled`;
- временное suppression только с reason и TTL;
- resume;
- retention status/dry-run/expired-only cleanup;
- freeze/unfreeze миссии.

Обычный пользователь не имеет доступа к настройкам и внутреннему trace.

## 9. Безопасность

Запрещено сохранять API keys, auth headers, cookies, passwords, prompts, chain-of-thought, полный raw provider response и приватные инфраструктурные адреса. Используются allowlist metadata, redaction, size limits и digest.

## 10. Admin diagnostics

Панель должна показывать:

- mission timeline;
- provider waterfall;
- data funnel `raw → normalized → deduplicated → entity resolved → evidence → report`;
- typed причины потерь;
- performance/resource pressure;
- current logging mode и retention status;
- safe JSONL diagnostic bundle.

Кнопка «Почему отчёт получился таким?» собирает безопасный диагностический пакет по mission/attempt.

## 11. Acceptance

- ordered durable events сохраняются после restart/redeploy;
- provider waterfall объясняет отсутствие данных;
- expired-only cleanup не удаляет минимальную историю;
- freeze/hold/active protections работают;
- resource pressure автоматически снижает стоимость записи;
- `WRITE_DISABLED` сохраняет минимальный bounded emergency trail;
- dropped event count наблюдаем;
- secrets/raw payloads отсутствуют;
- отказ ledger не ломает бизнес-поток;
- Baseline CI и exact-SHA stage acceptance зелёные.

## 12. Связанные задачи

- #293 — сквозной technological trace и provider data-flow;
- #297 — коммерческий end-to-end путь поиска и исследования компании;
- durable handoff — #173.

---

## English summary

The Site Auditor always emits all safe event classes and controls retention, aggregation and write cost independently. Cleanup is expired-only. Resource pressure degrades logging through bounded modes while preserving service availability and a minimal emergency ring-buffer trail. Provider and data funnels must explain where results were selected, returned, normalized, rejected and used.