# AIMETON Provisional Entity Resolution v0.1

Статус: provisional-срез `SA-SR-03 / #84` слит PR `#99` и развёрнут на stage.
Версия `0.15.0`, merge/deployment SHA
`de9f864b10b1cb1c340f0d8429273e4e908d650a`; PR Baseline CI `#30503294900`,
main Baseline CI `#30503376185` и Deploy Stage `#30503427439` — success.

Live HTTP-цикл на exact stage подтвердил создание process-local mission,
исполнение выданного `resolve_identity`, результат `provisional`, одну ревизию
history и пустой `accepted_identifier_links`. Provider action был только
сформирован как candidate и не выполнялся.

## Назначение

Слой получает provenance-bearing identity signals из bootstrap crawler и
строит управляемое представление неопределённости:

```text
BootstrapCrawlResult
  → проверка mission/correlation/document provenance
  → нормализация и валидация сигналов
  → competing identity candidates
  → provisional selection / conflict / unresolved
  → targeted search pivots
```

Результат питает следующий оборот Mission Orchestrator, но не открывает
Report Gate и не создаёт доказанный `EntityIdentifier`.

## API

```http
POST /api/missions/{mission_id}/resolve-identity
GET  /api/missions/{mission_id}/identity-history
```

POST принимает:

- последний выданный `NextActionPlan` с выбранным `resolve_identity`;
- один или несколько полностью сериализованных `BootstrapCrawlResult`.

Повтор с тем же `(mission_id, turn_number, input_digest)` идемпотентен.
Повтор того же plan с изменённым входом отклоняется.

## Fail-closed входной контракт

До разрешения проверяются:

1. plan действительно выдан текущим Mission Orchestrator;
2. plan принадлежит миссии и выбирает `resolve_identity`;
3. `mission_id`, `analysis_id` и `correlation_id` каждого bootstrap result
   совпадают с Mission Contract;
4. document IDs уникальны между входными пакетами;
5. signal ссылается на существующий документ;
6. `signal.source_url` совпадает с requested или final URL документа;
7. primary-document hint ссылается на существующую страницу;
8. `same_domain` для document hint пересчитывается по host.

Несогласованный пакет целиком отклоняется до записи новой ревизии.

## Нормализация и проверка

Детерминированно нормализуются:

- ИНН и ОГРН/ОГРНИП — только цифры и проверка контрольного разряда;
- телефон — цифры и единый `+7` для российского префикса `8`;
- email — нижний регистр и структурная проверка;
- наименование и адрес — Unicode-aware нормализация пробелов и знаков.

Невалидный сигнал сохраняется в `invalid_signals` вместе с документом,
locator, временем наблюдения и digest, но не входит в candidate identifier.

## Разделение кандидатов

Сильные идентификаторы ИНН/ОГРН объединяются между документами только по
точному нормализованному значению. Наименование связывается с реквизитами,
когда они однозначно находятся в одном документе.

Одинаковое наименование не является достаточным основанием объединить разные
ИНН/ОГРН. Такие записи сохраняются как competing candidates и создают
`same_name_different_identifiers`. Несколько юридических наименований рядом с
реквизитами в одном документе создают `ambiguous_document_attribution`.

Выбор provisional-кандидата требует:

- confidence не ниже `0.55`;
- отрыв от следующего кандидата не ниже `0.15`;
- отсутствие конфликта, блокирующего лидера.

Confidence ограничен `0.95`: bootstrap-сигналы не могут сами создать
`resolved`.

## Provenance и Evidence Guard

Каждый candidate identifier содержит:

- исходное и нормализованное значение;
- document ID и source URL;
- locator;
- `accessed_at`;
- normalized document digest.

Поле `accepted_identifier_links` в этом срезе всегда пусто. Для accepted link
потребуется фактически загруженный документ, Evidence Guard и схема
`EntityIdentifier/Evidence`. Поэтому результат `provisional`, `conflicting`
или `unresolved` физически не может быть выдан как разрешённая идентичность.

## Следующий оборот

Результат возвращает:

- `ActionOutcome`;
- рекомендуемый `SufficiencyFeedback` только для вопроса identity;
- `query_provider` по provisional-реквизитам или домену;
- same-domain `fetch_document` для найденных первичных документов;
- `review_conflict`, когда автоматическое объединение запрещено.

Эти записи являются кандидатами для Policy Guard. Endpoint не вызывает
Yandex, Tavily или другой provider и не расходует бюджет.

## История и граница v0.1

Новая успешно рассчитанная ревизия содержит `supersedes_result_id`; прежние
кандидаты и конфликты остаются доступными в identity history. Хранилище пока
process-local, как и Mission Orchestrator v0.1. Durable checkpoint и restart
recovery относятся к `#88`.

Срез не закрывает всю `#84`. Остаются:

- повышение identity link только после Evidence Guard;
- официальный registry/source verification;
- distinguishing brand, branch, owner и affiliated entity;
- human-review decision;
- Benchmark identity fixtures для «Дедала» и контрольного набора;
- интеграция с targeted crawler `#85` и УДП Evaluator `#86`.

## Проверка

```bash
python scripts/export_identity_resolution_schema.py
pytest -q tests/test_entity_resolution.py
pytest -q
```

Целевой набор проверяет provisional, competing conflict, checksum rejection,
revision history, inconsistent provenance, JSON Schema и настоящий HTTP-цикл.
