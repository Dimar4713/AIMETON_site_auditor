# AIMETON Site Auditor · Current Status

_Last updated: 2026-07-22_

## Текущее положение

**Фаза:** SA-01 — стабилизация поискового и MCP-контура.

**Завершено:**

- `SA-01.1` / Issue #9 — baseline и минимальный CI;
- `SA-01.2` / Issue #10 — MCP stage host/origin и proxy-safe redirect;
- `SA-01.3` / Issue #11 — устранён двойной внешний поиск;
- `SA-01.4` / Issue #12 — разделены тип запроса, тип результата и класс источника;
- `SA-01.5` / Issue #13 — разделены discovery hint, source candidate и evidence;
- `SA-01.6` / Issue #14 — обязательный объяснимый pre-score до глубокой обработки;
- `SA-01.7` / Issue #15 — детерминированный регрессионный пакет KIMI.

**Текущая контрольная точка:** готовность к Issue #16.

**Следующая подготовленная задача:** `SA-01.8 — Интеграционная проверка стабилизированного контура` / Issue #16.

**Текущий main до merge SA-01.7:** `c6a092a790e6197b70433449d299f1ea9409d791`.

## Зафиксированный baseline

- приложение: `AIMETON Site Auditor 0.6.1`;
- Python CI: `3.11`;
- полный `pytest` проходит;
- импорт приложения проходит;
- `/api/health` и регистрация `/mcp` проверяются автоматически;
- зависимости и pytest-output сохраняются как CI-артефакт.

## Результаты стабилизации

- SA-01.2: proxy-safe MCP redirect и защищённый Host/Origin;
- SA-01.3: один внешний поиск на company-intelligence цикл;
- SA-01.4: независимые `query_kind`, `result_kind`, `source_class`;
- SA-01.5: `discovery_hint → source_candidate → evidence`;
- SA-01.6: обязательный объяснимый pre-score до deep processing;
- SA-01.7: KIMI fixtures и runtime/golden regression tests без внешней сети и секретов.

## Регрессионный пакет KIMI

- покрывает классификацию news/jobs, court, official и unknown;
- проверяет, что поисковый сниппет не является evidence;
- проверяет один provider call и статус `partial` без verified evidence;
- закрепляет high-score и `insufficient_data` pre-score cases;
- golden outputs изменяются только с версией fixture и нормативным обоснованием.

## Подготовленный Epic SA-01

- #9–#15 — завершены после merge соответствующих PR;
- #16 — интеграционная проверка — следующий кандидат.

## Правило продолжения

```text
одна Issue
→ одна ограниченная ветка
→ один проверяемый PR
→ зелёный CI
→ наблюдаемый результат
→ обновление CURRENT_STATUS.md
→ Project status Done
```

## Оперативное управление

Состояние синхронизируется через `CURRENT_STATUS.md`, GitHub Issues, Project-доску, Pull Requests и tests / CI / validation evidence.
