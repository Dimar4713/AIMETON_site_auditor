# AIMETON Site Auditor

Экспериментальный орган экономической разведки AIMETON. Работает в трёх режимах:

1. анализ конкретного сайта по URL;
2. автономная «охота» по заданной территории и параметрам поиска;
3. рабочая разведка конкретной компании с новостным, справочным, отзывным и кадровым фоном.

Возможности доступны через UI, REST API и MCP Streamable HTTP.

## Справочник охотника

`app/hunter_handbook.py` задаёт расширяемое пространство вариантов, по которому агент планирует охоту и классифицирует найденные компании:

- отрасли и их поисковые синонимы;
- бизнес-модели;
- типовые экономические сигналы и проблемные ситуации;
- подходящие классы AI-продуктов;
- связи «отрасль → бизнес-модель → сигнал → продукт».

Справочник не является закрытым перечнем. Неизвестная отрасль не отбрасывается: агент создаёт пользовательскую категорию и помечает её как кандидата на последующее пополнение справочника.

Получить справочник программно:

```http
GET /api/hunter-handbook
```

## Принцип работы охоты

Пользователь задаёт рамку: регион, дополнительную зону, отрасли, фокус и лимиты. Агент формирует запросы, находит сайты, исключает агрегаторы и дубли, проверяет территорию, оценивает коммерческую возможность и глубоко прорабатывает лучшие цели.

Каноническая цепочка:

```text
обнаружение экономических сигналов
→ квалификация и формирование коммерческого контура
→ подготовка и передача коммерческой возможности
```

## API

Swagger/OpenAPI после запуска:

```text
/docs
```

### Анализ конкретного сайта

```http
POST /api/analyze
Content-Type: application/json

{"url":"https://example.ru"}
```

### Рабочая разведка компании

```http
POST /api/company-intelligence
Content-Type: application/json

{
  "company_name": "Sib Dental Clinic",
  "url": "https://sibdentalclinic.ru",
  "region": "Красноярск",
  "max_sources": 20
}
```

Результат включает разведочный анализ сайта, классифицированные источники,
уровень доказательности, информационный запах, коммерческий балл и честный
статус полноты `complete`/`partial`. Это исследовательский контур; проверяемый
Company Profile v1 строится отдельным SEF endpoint ниже.
Поле `search` показывает состояние Provider Gateway, fallback, задержку и оценочную стоимость без раскрытия запроса или ключей.

`GET /api/search/health` различает настройку и реальную готовность provider.
Возможные состояния: `active`, `not_configured`, `pricing_unknown`,
`budget_blocked`, `quota_blocked`, `circuit_open`. Для платного provider
нулевая или неизвестная цена закрывает вызов; `configured=true` само по себе
не означает `active`.

### Поисковая миссия

Все новые входы создают канонический Mission Contract:

```http
POST /api/missions
GET /api/missions/{mission_id}
POST /api/missions/{mission_id}/plan
POST /api/missions/{mission_id}/turns
POST /api/missions/{mission_id}/bootstrap-crawl
POST /api/missions/{mission_id}/resolve-identity
GET  /api/missions/{mission_id}/identity-history
```

UI/REST/MCP используют один builder контракта. `/api/analyze` сохранён как
backward-compatible adapter: он создаёт изолированные `mission_id` и
`analysis_id`, записывает preliminary turn и не может объявить L0-результат
завершённой поисковой миссией.

Bootstrap crawler исполняет только выданный `crawl_url` plan. Перед запросом
он проверяет robots, SSRF и domain allowlist, затем ограниченно получает
главную, релевантные same-domain страницы и sitemap hints. Identity signals
остаются `candidate`, а ссылки на PDF/DOCX — `discovery_hint`, пока документ не
загружен и не прошёл Evidence Guard.

Provisional Entity Resolution исполняет только выданный `resolve_identity`
plan. Он перепроверяет mission/document provenance, контрольные разряды
ИНН/ОГРН, сохраняет competing candidates и конфликты, а затем возвращает
targeted search pivots. Даже выбранный provisional-кандидат не содержит
accepted identity links и не открывает клиентский выпуск.

### Проверяемый Company Profile v1

```http
POST /api/sef/company-profile
Content-Type: application/json

{
  "bundle": {"schema_version": "0.1.0", "...": "..."},
  "ledger_request": {
    "schema_version": "0.1.0",
    "mission_id": "mission_...",
    "as_of": "2026-07-28T12:00:00Z",
    "evidence_metadata": []
  },
  "entity_id": "entity_..."
}
```

Endpoint сам пересчитывает Ledger snapshot и возвращает 14 секций, шесть
critical-gap assessment и приложение документных доказательств. Успешный
`profile_gate_passed` сам по себе не разрешает выдачу клиенту.

### Human Review и Report v1

Выпуск выполняется в два шага:

```http
POST /api/sef/report/review-package
POST /api/sef/report
POST /api/sef/report.html
POST /api/sef/report.md
POST /api/sef/report.docx
```

Первый endpoint пересчитывает Ledger и Company Profile и возвращает точные
`profile_digest`, `evidence_appendix_digest` и `release_control_digest` для
проверки человеком. Release control показывает фактические УДП, identity,
execution integrity, обязательные вертикали, providers и budget. Следующие
endpoints принимают human sign-off, привязанный к этим digest, повторно
пересчитывают snapshot и выпускают JSON, печатный HTML, Markdown или
редактируемый Word `.docx` только при прохождении fail-closed шлюза. Клиент не
может передать готовый профиль, Ledger snapshot или
`client_release_ready=true`.

В интерфейсе предварительный результат можно выгрузить в PDF, Markdown или
Word. PDF больше не включает диалог с консультантом. Markdown и Word строятся
из структурированного объекта анализа и явно помечаются как предварительные;
они не заменяют подписанный Report v1. Диалог хранится отдельно для каждого
`analysis_id`, поэтому переключение истории не смешивает сообщения разных
компаний. Эвристический fallback маркируется как `preliminary_hypothesis`, а
UI/API/экспорт раздельно показывают УДП, identity, полноту профиля, качество
evidence, коммерческий приоритет, budget и физические блокеры выпуска.

Контракт, reason codes и границы P0 описаны в
[`docs/architecture/SEF_HUMAN_REVIEW_REPORT_V1.md`](docs/architecture/SEF_HUMAN_REVIEW_REPORT_V1.md).

### Запрос на охоту

```http
POST /api/hunt
Content-Type: application/json

{
  "region": "Красноярск и Красноярский край",
  "search_zone": "Красноярская агломерация",
  "industries": ["отопление и вентиляция", "промышленное оборудование"],
  "focus": ["сложный подбор", "повторяющиеся консультации"],
  "max_candidates": 100,
  "deep_audit_score": 60,
  "output_limit": 25
}
```

Пустой список `industries` означает охоту по полному справочнику.
Машинно-читаемое поле `search.state` принимает `success`, `degraded` или `unavailable`.

## Тактический план Search & Evidence Fabric

Переход от текущего контура разведки к повторяемому продаваемому доказательному профилю компании ведётся по этапам SEF-P0: контракты миссии и доказательств, Provider Gateway, загрузка документов, Claim & Evidence Ledger, PostgreSQL/pgvector, Company Profile v1, Benchmark-20 и внешняя приёмка.

- [Тактический план доработки инфраструктуры и AIMETON Site Auditor](docs/plans/AIMETON_SEF_tactical_plan_2026-07-28.md)

## MCP

MCP Streamable HTTP разделён на два профиля:

```text
/mcp/        — public read-only profile
/mcp-admin/  — administrative profile с Bearer token
```

Публичные инструменты:

- `analyze_site` — анализ конкретного сайта;
- `hunt_companies` — отраслевая охота;
- `company_intelligence` — разведочный профиль компании; проверяемый SEF
  Company Profile v1 доступен через REST API.

Административные инструменты не публикуются в public profile. Admin endpoint работает fail-closed и требует секрет `AIMETON_MCP_ADMIN_TOKEN`.

Для обоих профилей действуют rate limiting, ограничение конкурентности, `X-Request-ID`, DNS rebinding protection и санитарно очищенный audit trail.

Полное описание архитектуры, подключения клиентов, правил использования, ротации токена и эксплуатационной проверки: [`docs/MCP-SECURITY.md`](docs/MCP-SECURITY.md).

Используется стабильная линия официального MCP Python SDK:

```text
mcp>=1.25,<2
```

## Переменные окружения

```text
ROUTERAI_API_KEY=...
ROUTERAI_MODEL=...
SEARCH_PROVIDER_ORDER=yandex,searxng,tavily
SEARCH_TIMEOUT_SECONDS=15
SEARCH_RETRIES=1
SEARCH_CACHE_TTL_SECONDS=900
SEARCH_ALLOW_PAID_FALLBACK=false
SEARXNG_BASE_URL=https://your-searxng-instance.example
YANDEX_SEARCH_API_KEY=...
YANDEX_SEARCH_FOLDER_ID=...
YANDEX_SEARCH_COST_RUB=...
SEARCH_MISSION_BUDGET_RUB=...
TAVILY_API_KEY=...
TAVILY_SEARCH_COST_USD=...
SEARCH_MISSION_BUDGET_USD=...
CRAWL4AI_BASE_URL=http://crawl4ai:11235
CRAWL4AI_API_TOKEN=...
AIMETON_MCP_ADMIN_TOKEN=...
AIMETON_MCP_PUBLIC_RATE_LIMIT=30
AIMETON_MCP_ADMIN_RATE_LIMIT=20
AIMETON_MCP_RATE_WINDOW_SECONDS=60
AIMETON_MCP_MAX_CONCURRENCY=4
```

Без ключа RouterAI используется резервный эвристический анализ. Ненастроенные поисковые адаптеры пропускаются; если недоступны все разрешённые провайдеры, внешний OSINT-контур возвращает `partial`, а `search.state` — `unavailable`.

Безопасное состояние провайдеров без ключей и заголовков:

```http
GET /api/search/health
```

Подробный контракт и политика стоимости: [`docs/architecture/SEF-PROVIDER-GATEWAY-V0.1.md`](docs/architecture/SEF-PROVIDER-GATEWAY-V0.1.md).

Контур документов сначала использует безопасный HTTP, затем при необходимости
отдельный Crawl4AI worker и только после него ограниченный browser fallback.
Поисковый snippet остаётся `discovery_hint`; evidence создаётся лишь из
загруженного документа по проверенной цитате и locator. Контракт:
[`docs/architecture/SEF-DOCUMENT-FETCH-EXTRACT-V0.1.md`](docs/architecture/SEF-DOCUMENT-FETCH-EXTRACT-V0.1.md).

Если `AIMETON_MCP_ADMIN_TOKEN` отсутствует, административный MCP endpoint остаётся заблокированным и возвращает `401`.

## Запуск

1. Импортируйте репозиторий в Replit или разверните на Linux-сервере.
2. Добавьте secrets.
3. Выполните `pip install -r requirements.txt`.
4. Запустите:

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5000}
```

Для Replit добавлен `.replit`. Подробная инструкция: `docs/DEPLOY_REPLIT_API_MCP.md`.

## Безопасность

- ключи и административные токены хранятся только в secret storage и переменных окружения;
- public и admin MCP tools разделены по разным endpoints;
- admin MCP защищён Bearer token и работает fail-closed;
- rate limiting и concurrency limits защищают MCP от неконтролируемой нагрузки;
- SSRF-защита блокирует локальные и служебные IP;
- DNS rebinding protection и явные host/origin allowlists сохраняются;
- ограничены тип, размер и время загрузки страницы;
- audit trail не содержит токенов, JSON-RPC parameters и пользовательских запросов;
- неподтверждённые упоминания не выдаются за факты;
- LLM не получает право самостоятельно выполнять внешние коммерческие действия.

Подробные правила: [`docs/MCP-SECURITY.md`](docs/MCP-SECURITY.md).

## Тесты

```bash
pytest -q
```

Изменения экспериментальной ветки требуют повторного прогона тестов и проверки на реальном stage-домене перед публикацией.
