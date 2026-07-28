# AIMETON SEF Provider Gateway v0.1

**Статус:** исполняемый контракт SA-SEF-02  
**Версия:** 0.1.0  
**Назначение:** отделить бизнес-логику Site Auditor от конкретных поисковых сервисов и сделать fallback, стоимость и деградацию наблюдаемыми.

## 1. Канонический маршрут

```text
mission
→ cache
→ policy / budget / quota / circuit
→ Yandex | SearXNG | Tavily
→ canonical URL + dedupe
→ discovery_hint
```

Кэш проверяется до внешних провайдеров. Поисковый результат остаётся `discovery_hint` и не становится evidence без загрузки первичного документа.

## 2. Контракт

Все адаптеры принимают `SearchRequest` и возвращают `list[SearchItem]`. Бизнес-логика не знает их HTTP endpoints, схемы авторизации и исходные форматы ответа.

`SearchDiagnostics` содержит:

- состояние `success`, `degraded` или `unavailable`;
- выбранного провайдера;
- факт cache hit и fallback;
- fingerprint запроса вместо текста запроса;
- latency, result count и reason code каждой попытки;
- оценочную стоимость по валютам.

Ключи, заголовки авторизации и текст запроса в диагностику не входят.

## 3. Адаптеры

| Адаптер | Транспорт | Роль |
|---|---|---|
| `SearxngProvider` | `GET /search?format=json` | собственный бесплатный резерв |
| `YandexProvider` | `POST /v2/web/search`, Base64 XML | основной российский поиск при заданном бюджете |
| `TavilyProvider` | `POST /search`, `basic` | ограниченный платный fallback |

Форматы сверены с официальной документацией:

- [Yandex Web Search REST API](https://yandex.cloud/en/docs/search-api/api-ref/WebSearch/search)
- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)

## 4. Fail-closed политика стоимости

Платный провайдер вызывается только если:

1. он настроен;
2. для него задана ненулевая оценочная стоимость вызова;
3. в политике миссии есть достаточный бюджет соответствующей валюты;
4. глобальная квота не исчерпана;
5. платный fallback явно разрешён, если до него уже выполнялся другой провайдер.

Повторный платный вызов повторно резервирует бюджет и квоту. Поэтому retry не может скрытно превысить лимит миссии.

## 5. Fallback и circuit breaker

Reason codes:

- `not_configured`;
- `policy_blocked`;
- `budget_exceeded`;
- `quota_exceeded`;
- `circuit_open`;
- `timeout`;
- `provider_error`;
- `empty_results`.

Отказ одного провайдера не завершает миссию. После порога последовательных ошибок circuit открывается, а по истечении recovery interval допускает пробный вызов.

## 6. Конфигурация

```text
SEARCH_PROVIDER_ORDER=yandex,searxng,tavily
SEARCH_TIMEOUT_SECONDS=15
SEARCH_RETRIES=1
SEARCH_CACHE_TTL_SECONDS=900
SEARCH_ALLOW_PAID_FALLBACK=false

SEARXNG_BASE_URL=http://searxng:8080

YANDEX_SEARCH_API_KEY=...
YANDEX_SEARCH_FOLDER_ID=...
YANDEX_SEARCH_COST_RUB=...
SEARCH_MISSION_BUDGET_RUB=...
SEARCH_QUOTA_YANDEX=...

TAVILY_API_KEY=...
TAVILY_SEARCH_COST_USD=...
SEARCH_MISSION_BUDGET_USD=...
SEARCH_QUOTA_TAVILY=...
```

Ненастроенные адаптеры пропускаются. При текущем stage-наборе без платных ключей Gateway продолжает работать через SearXNG.

## 7. Наблюдаемость

`GET /api/search/health` возвращает только:

- настроен ли провайдер;
- платный ли он;
- состояние circuit breaker;
- остаток локальной глобальной квоты.

Ответы `/api/hunt` и `/api/company-intelligence` включают машинно-читаемое поле `search`.

## 8. Границы v0.1

- TTL cache пока process-local, но изолирован отдельным контрактом для последующей замены на Valkey.
- Счётчики бюджета и квоты process-local; устойчивое распределённое хранение относится к инфраструктурному этапу PostgreSQL/Valkey.
- Стоимость является конфигурируемой оценкой, а не заменой сверки счёта провайдера.
- Поисковые сниппеты не являются evidence.

## 9. Приёмка

- один contract test выполняется для SearXNG, Yandex и Tavily;
- проверены fallback, circuit breaker, retry budget, quota/cache, dedupe и sanitization;
- Provider Gateway Benchmark-5 фиксирует recall, latency и стоимость;
- полный baseline CI остаётся обязательным merge-gate.

Запуск измерения на настроенных провайдерах:

```bash
python scripts/run_provider_gateway_benchmark.py \
  --output evidence/provider-gateway/benchmark-5.json
```

Результат не содержит текста запросов и секретов; сохраняются только ID кейса, ожидаемый host, состояние, провайдер, latency, количество результатов и стоимость.
