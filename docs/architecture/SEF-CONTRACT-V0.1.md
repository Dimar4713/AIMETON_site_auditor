# AIMETON Search & Evidence Fabric — контракт v0.1

## Назначение

Контракт отделяет доказательный профиль от конкретного поискового провайдера и
сохраняет сквозную трассу Runtime Core:

```text
runtime task
→ mission
→ provider call
→ discovery hint
→ fetched document
→ evidence
→ claim
→ review
→ report
```

Версия схемы: `0.1.0`.

## Канонические артефакты

- Pydantic-модель: `app/sef/models.py`;
- JSON Schema: `schemas/sef-v0.1.schema.json`;
- генератор схемы: `scripts/export_sef_schema.py`;
- начальная переносимая SQL-миграция:
  `migrations/sef/0001_sef_v0_1.sql`;
- положительная цепочка:
  `tests/fixtures/sef/positive-chain-v0.1.json`;
- отрицательная цепочка:
  `tests/fixtures/sef/forbidden-snippet-confirmed-v0.1.json`.

## Инварианты

1. Поисковый сниппет остаётся `discovery_hint` и не является evidence.
2. Evidence возникает только из успешно загруженного документа и содержит
   цитату, locator, время наблюдения и SHA-256.
3. Claim `confirmed` требует доказательство с отношением `supports`.
4. Claim `contradicted` требует доказательство с отношением `contradicts`.
5. Противоречащие claims сохраняются отдельными записями и не затирают друг
   друга.
6. `not_found` допустим только после завершённого search plan минимум с одним
   выполненным запросом.
7. LLM отсутствует среди допустимых видов источников: модель может
   интерпретировать evidence, но не создавать происхождение факта.
8. Критичный неподтверждённый claim не включается в клиентский report.
9. `correlation_id` совпадает на всём пути mission → provider call → evidence.

## Граница с Runtime Core

`mission.runtime_task_id` связывает SEF с существующей задачей Runtime Core.
Runtime Core v0.1 продолжает использовать SQLite. SEF-хранилище развивается
отдельно и может быть перенесено в PostgreSQL без изменения транспортного
контракта.

## Проверка

```bash
python scripts/export_sef_schema.py
pytest -q tests/test_sef_contract_v0_1.py
```

Тесты проверяют синхронность Pydantic и JSON Schema, SQL-миграцию, разрешённую
цепочку `hint → document → evidence → claim`, запрещённое повышение сниппета,
правило `not_found`, защиту клиентского отчёта и выражение Golden-5 без
provider-specific полей.
