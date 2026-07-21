# AIMETON Site Auditor · детальный план реализации Evidence Memory и RAG

## 1. Цель

Поэтапно создать первый сохраняющий контур экономической разведки, который:

- не теряет собранные материалы;
- хранит оригиналы, версии и provenance;
- поддерживает текстовые, табличные и графические данные;
- даёт гибридный поиск и RAG;
- отделяет первичные источники от фактов, гипотез и рекомендаций;
- не блокирует дальнейший переход к Graph RAG и онтологии AIMETON;
- реализуется простыми проверяемыми действиями.

## 2. Границы первого MVP

### Входит

- MinIO/S3-compatible object storage;
- PostgreSQL metadata/provenance;
- Evidence Ingestion Gateway;
- SHA-256 дедупликация;
- версии источников;
- OpenRAG/OpenSearch;
- Docling processing;
- коллекции `raw_evidence`, `verified_claims`, `analytical_views`, `investigation_outputs`;
- интеграция с текущим Site Auditor;
- ссылки на первоисточники;
- базовая обработка PDF, HTML, JSON, изображений и таблиц;
- REST/MCP retrieval;
- резервное копирование.

### Не входит

- полная Palantir-подобная онтология;
- автоматическое построение глобального knowledge graph;
- тяжёлый Visual RAG с обязательной GPU;
- автоматическая установка непроверенных внешних инструментов;
- хранение скрытых цепочек рассуждений моделей;
- автономные внешние коммерческие действия.

## 3. Архитектурные компоненты

```text
Site Auditor Collectors
        ↓
Evidence Ingestion Gateway
        ├── Raw Object Store / MinIO
        ├── PostgreSQL Metadata and Provenance
        ├── Processing Queue
        └── OpenRAG/OpenSearch Indexing
                 ↓
Evidence Retrieval Gateway
        ├── REST
        ├── MCP
        ├── Report Composer
        └── AIMETON cognitive modules
```

## 4. Порядок реализации

# M0. Подготовка и фиксация контрактов

**Цель:** до развёртывания инфраструктуры определить форматы и границы.

### Простые действия

- [ ] Создать `app/evidence/`.
- [ ] Создать схемы `Investigation`, `EvidenceSource`, `EvidenceDocument`, `EvidenceAsset`, `ProcessingJob`.
- [ ] Зафиксировать ID-префиксы: `INV`, `MIS`, `SRC`, `DOC`, `AST`, `CLM`.
- [ ] Определить допустимые MIME-типы.
- [ ] Определить лимиты размера.
- [ ] Определить retention policy.
- [ ] Определить состояния обработки.
- [ ] Добавить feature flag `EVIDENCE_MEMORY_ENABLED`.
- [ ] Добавить ADR о выборе OpenRAG как заменяемой реализации.

### Состояния документа

```text
discovered
→ stored
→ normalized
→ indexed
→ verified / rejected
→ superseded / archived
```

### Definition of Done

- схемы проходят Pydantic validation;
- ID генерируются детерминированно;
- feature flag не меняет текущую работу сервиса;
- контракт покрыт unit tests.

---

# M1. Хранилище оригиналов

**Цель:** начать сохранять всё полученное до подключения RAG.

### Простые действия

- [ ] Добавить MinIO в локальный `docker-compose`.
- [ ] Создать bucket `aimeton-evidence`.
- [ ] Реализовать `ObjectStore` interface.
- [ ] Реализовать `MinioObjectStore`.
- [ ] Считать SHA-256 до записи.
- [ ] Проверять дедупликацию по hash.
- [ ] Хранить content type, size и original filename.
- [ ] Хранить raw HTML страниц.
- [ ] Хранить raw JSON ответов API.
- [ ] Хранить PDF и изображения.
- [ ] Добавить endpoint внутренней диагностики object store.

### Критерии приёмки

- повторная загрузка одинакового файла не создаёт вторую копию;
- оригинал скачивается по внутреннему object key;
- повреждение выявляется повторной проверкой hash;
- отказ MinIO не ломает старый анализ при выключенном feature flag.

---

# M2. PostgreSQL Metadata and Provenance

**Цель:** знать происхождение каждого объекта и контекст его получения.

### Простые действия

- [ ] Добавить PostgreSQL/Alembic.
- [ ] Создать таблицы `investigations`, `missions`, `sources`, `documents`, `assets`, `versions`, `processing_jobs`.
- [ ] Связать source с provider и query.
- [ ] Сохранить `search_branch`, `search_plane`, `perspective`, `rptk_refs`.
- [ ] Сохранить `published_at`, `retrieved_at`, `valid_from`, `valid_to`.
- [ ] Сохранить `persistence_policy` и `license_notes`.
- [ ] Добавить source class и evidence status.
- [ ] Реализовать repository layer.
- [ ] Добавить миграционные тесты.

### Definition of Done

- любой object key разрешается в карточку provenance;
- история версий источника доступна одним запросом;
- удаление индекса OpenRAG не удаляет оригиналы и метаданные;
- backup/restore PostgreSQL проверен на тестовой базе.

---

# M3. Evidence Ingestion Gateway

**Цель:** все сборщики пишут в память через один контракт.

### Простые действия

- [ ] Реализовать `ingest_evidence()`.
- [ ] Принять bytes, URL reference или structured JSON.
- [ ] Валидировать MIME, размер и URL.
- [ ] Создать source/document/version records.
- [ ] Сохранить оригинал.
- [ ] Поставить processing job.
- [ ] Вернуть `source_id`, `document_id`, `status`.
- [ ] Добавить idempotency key.
- [ ] Добавить retry policy.
- [ ] Добавить журнал ошибок без секретов.
- [ ] Интегрировать с `fetch_site`.
- [ ] Интегрировать с внешним OSINT collector.

### Критерии приёмки

- одна операция либо создаёт согласованный набор записей, либо откатывается;
- повтор с тем же idempotency key безопасен;
- поисковый сниппет хранится как discovery hint, а не verified evidence;
- каждый собранный сайт имеет raw HTML и metadata record.

---

# M4. OpenRAG/OpenSearch

**Цель:** получить первый гибридный RAG над накопленными материалами.

### Простые действия

- [ ] Подготовить отдельный compose profile для OpenRAG.
- [ ] Настроить OpenSearch snapshots.
- [ ] Настроить русскоязычные embeddings через поддерживаемый endpoint.
- [ ] Настроить Docling parsing.
- [ ] Создать adapter `HybridRetrievalProvider`.
- [ ] Реализовать upload/index status mapping.
- [ ] Передавать metadata filters.
- [ ] Добавить full-text + vector retrieval.
- [ ] Добавить reranking.
- [ ] Подключить REST.
- [ ] Подключить MCP в ограниченном read-only режиме.
- [ ] Добавить health checks.

### Тестовый корпус

Использовать:

- отчёты тестирования KIMI;
- PDF отчёты Site Auditor;
- HTML нескольких тестовых компаний;
- JSON API ответов;
- одну таблицу XLSX/CSV;
- несколько изображений страниц.

### Definition of Done

- система находит конкретный документ и нужный фрагмент;
- ответ содержит source/document/page identifiers;
- metadata filters работают по company, investigation и source class;
- OpenRAG можно отключить без потери оригиналов;
- индекс перестраивается из Object Store + PostgreSQL.

---

# M5. Разделение пространств знаний

**Цель:** не допустить самоподтверждения гипотез через смешанный индекс.

### Простые действия

- [ ] Создать логические пространства `raw_evidence`.
- [ ] Создать `verified_claims`.
- [ ] Создать `analytical_views`.
- [ ] Создать `investigation_outputs`.
- [ ] Ввести обязательный `knowledge_class`.
- [ ] Запретить перенос analytical view в verified claims без verifier step.
- [ ] Добавить retrieval policy по типу задачи.
- [ ] Добавить UI-фильтр класса знания.

### Definition of Done

- запрос «только первичные источники» не возвращает старые рекомендации;
- гипотеза визуально и машинно отличается от факта;
- отчёт указывает класс каждого утверждения;
- verified claim имеет хотя бы одну EvidenceLink.

---

# M6. Документы, таблицы и графика

**Цель:** не терять смысл нетекстовых материалов.

### Простые действия

- [ ] Рендерить страницы PDF в PNG/WebP.
- [ ] Сохранять page number и bounding metadata.
- [ ] Извлекать таблицы в Markdown/JSON.
- [ ] Сохранять OCR отдельно от основного текста.
- [ ] Создавать visual description.
- [ ] Индексировать caption и visual entities.
- [ ] Давать ссылку на исходное изображение страницы.
- [ ] Не считать VLM description первичным фактом.
- [ ] Добавить quality flag для OCR/table extraction.

### Definition of Done

- по вопросу о графике находится нужная страница;
- таблица доступна и как изображение, и как структура;
- пользователь может открыть первоисточник;
- неуспешное распознавание явно маркируется.

---

# M7. Интеграция с отчётом Site Auditor

**Цель:** отчёт становится входом в доказательную память, а не конечным тупиком.

### Простые действия

- [ ] Добавить source links рядом с фактами.
- [ ] Добавить Evidence drawer в UI.
- [ ] Показывать точную цитату и страницу.
- [ ] Добавить completeness по контурам.
- [ ] Добавить список неразрешённых противоречий.
- [ ] Сохранять финальный HTML/PDF в `investigation_outputs`.
- [ ] Сохранять параметры генерации отчёта.
- [ ] Добавить кнопку повторного исследования с использованием памяти.

### Definition of Done

- любой значимый вывод раскрывается до первоисточника;
- PDF содержит стабильные IDs источников;
- новое исследование может переиспользовать старые документы;
- пустые данные формируют план доразведки.

---

# M8. РПТК11 и многоперспективная память

**Цель:** сохранять не только итоговый синтез, но различимые взгляды.

### Простые действия

- [ ] Добавить модель `PerspectiveObservation`.
- [ ] Хранить observations, assumptions, blind_spots, confidence.
- [ ] Реализовать explicit/hidden, figure/background, part/whole, scale, time, causality, relations, intent/runtime views.
- [ ] Сохранять agreements и contradictions.
- [ ] Сохранять competing interpretations.
- [ ] Добавить disconfirming evidence.
- [ ] Добавить residual uncertainty.
- [ ] Реализовать критерий достаточной комплексности.

### Definition of Done

- первая интерпретация не перезаписывает альтернативы;
- provenance каждого взгляда доступен;
- слабый сигнал можно реактивировать;
- комплексный синтез показывает остаточную неопределённость.

---

# M9. Фрактальные ветви и усушение поиска

**Цель:** управлять ростом исследования и стоимостью.

### Простые действия

- [ ] Создать `SearchBranch` с parent/child relation.
- [ ] Добавить fractal level.
- [ ] Добавить связь ветви с РПТК4/target state.
- [ ] Рассчитывать relevance, information gain, evidence potential, cost.
- [ ] Ввести состояния active/productive/saturated/suspended/pruned/reactivated.
- [ ] Хранить причину усушения.
- [ ] Хранить условия реактивации.
- [ ] Добавить лимиты глубины, времени и бюджета.

### Definition of Done

- система объясняет, почему ветвь продолжена или остановлена;
- усушенная ветвь не удаляется;
- новая информация способна реактивировать ветвь;
- поиск завершается по критерию достаточности, а не только по timeout.

---

# M10. Capability Registry

**Цель:** отделить требуемую способность от конкретного инструмента.

### Простые действия

- [ ] Создать Capability Contract schema.
- [ ] Зарегистрировать OpenRAG.
- [ ] Зарегистрировать MinIO Object Store.
- [ ] Зарегистрировать Docling parser.
- [ ] Зарегистрировать поисковые и OSINT providers.
- [ ] Хранить ограничения, стоимость, доверие и заменяемость.
- [ ] Реализовать `ResolveCapability`.
- [ ] Поддержать Reuse → Compose → Acquire → Generate → Escalate.

### Definition of Done

- OpenRAG можно заменить другим provider через adapter;
- бизнес-логика не зависит от SDK конкретного RAG;
- capability gap формализуется до поиска нового инструмента;
- непроверенный инструмент не получает автоматического доступа к данным.

## 5. Приоритеты

### P0 — начать немедленно

- M0 контракты;
- M1 оригиналы;
- M2 provenance;
- M3 Evidence Gateway.

### P1 — первый полезный RAG

- M4 OpenRAG;
- M5 разделение пространств;
- M7 источники в отчёте.

### P2 — разнородные данные

- M6 графика и таблицы;
- версионность и temporal retrieval.

### P3 — воплощение AIMETON

- M8 РПТК11;
- M9 фрактальные ветви;
- M10 Capability Registry.

## 6. Первый исполнимый спринт

### Спринт EM-01

**Результат:** Site Auditor сохраняет оригинал проанализированной HTML-страницы и её provenance, не меняя текущий публичный ответ API.

#### Задачи

1. Создать модели M0.
2. Добавить feature flag.
3. Добавить MinIO compose service.
4. Реализовать ObjectStore interface.
5. Сохранить raw HTML после `fetch_site`.
6. Сохранить SHA-256.
7. Создать минимальную PostgreSQL запись source/document.
8. Добавить unit и integration tests.
9. Проверить работу при выключенном flag.
10. Проверить graceful degradation при недоступности памяти.

#### Приёмка

```text
POST /api/analyze
→ обычный ответ Site Auditor
+ в Evidence Memory появился исходный HTML
+ сохранены URL, hash, time, investigation ID
```

## 7. Общие требования качества

- никакие ключи и персональные данные не пишутся в логи;
- SSRF-защита сохраняется;
- сырые данные и аналитика разделены;
- схемы версионируются;
- каждый background job идемпотентен;
- каждый внешний provider имеет timeout/circuit breaker;
- хранение соответствует лицензии источника;
- индексы не являются source of truth;
- все критические операции покрываются тестами;
- изменения внедряются небольшими PR.

## 8. Контрольные точки

| Контрольная точка | Результат |
|---|---|
| CP1 | Оригиналы сохраняются и дедуплицируются |
| CP2 | Provenance восстанавливается из PostgreSQL |
| CP3 | OpenRAG находит тестовые материалы |
| CP4 | Факты и гипотезы разделены |
| CP5 | PDF/таблицы/изображения не теряются |
| CP6 | Отчёт раскрывается до источников |
| CP7 | РПТК11 хранит разные перспективы |
| CP8 | Ветви поиска управляемо усушаются |
| CP9 | RAG provider заменяем через capability adapter |

## 9. Принцип исполнения

Каждый этап выполняется по РПТК2 как последовательность простых действий:

```text
малое изменение
→ тест
→ наблюдаемый результат
→ фиксация опыта
→ следующий шаг
```

Не начинать следующий крупный слой, пока предыдущий не даёт воспроизводимый наблюдаемый результат.