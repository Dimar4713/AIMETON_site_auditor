# SEF Document Fetch/Extract v0.1

Статус: реализованный P0-контракт `SA-SEF-03`; расширение `SA-SR-01 / #82`
реализуется в рабочей ветке и до merge/deploy не является фактом stage.

## Назначение

Контур превращает `discovery_hint` в загруженный документ. Evidence появляется
отдельным действием и только тогда, когда дословная цитата найдена по стабильному
locator внутри этого документа.

```text
discovery_hint
→ URL/DNS/SSRF validation
→ static HTTP
→ BOM / HTTP charset / meta charset / detector
→ Crawl4AI worker
→ bounded browser fallback
→ normalized document + digest
→ verified quote + locator
→ evidence
```

Поисковый snippet не передаётся в `promote_quote()` и не может сам подтвердить
claim.

## Компоненты

| Компонент | Ответственность |
|---|---|
| `DocumentPipeline` | orchestration, concurrency=2, fallback и promotion |
| `StaticHttpFetcher` | HTTP-first, redirect validation, MIME/size/timeout limits и детерминированное декодирование |
| `Crawl4AIHttpWorker` | заменяемый self-hosted dynamic worker |
| `PlaywrightFallback` | последний ограниченный путь динамического рендеринга |
| `extract_html()` | header, все смысловые области body, footer, таблицы, ссылки, canonical и locators |
| `MemoryDocumentCache` | TTL cache неизменившегося документа в P0 |

Постоянное хранение оригиналов и PostgreSQL metadata входят в `SA-SEF-04` /
`INFRA-SEF-02`, а не маскируются памятью процесса.

## Инварианты

1. На каждом HTTP redirect повторяется DNS/SSRF validation.
2. Private, loopback, link-local, reserved, multicast и metadata-addresses
   запрещены.
3. Размер, redirects, timeout и concurrency ограничены политикой.
4. Ошибка worker/browser возвращается как контролируемый `FetchError`.
5. Динамический worker не вызывается после fail-closed ошибки безопасности или
   превышения размера.
6. У документа есть SHA-256 сырого HTML и нормализованного текста.
7. `Document.content_digest` равен digest нормализованного текста.
8. Document ID детерминирован по mission, source, canonical URL и digest.
9. Evidence ID детерминирован по document, locator и quote digest.
10. Диагностика содержит fingerprint, path, latency, size и cache hit, но не
    текст документа, query string URL, headers или token.
11. SHA-256 сырого содержимого считается по исходным байтам до декодирования.
12. Кодировка определяется строго в порядке `BOM → HTTP → meta → detector`;
    недостоверный результат завершается `encoding_undetermined`.
13. Redirect history сохраняет status, origins и digest URL без query string.
14. `rel=canonical` сохраняется как заявленная связь. Разные scheme или host
    не склеиваются автоматически и требуют Entity Resolution.
15. Header и footer извлекаются раздельно, чтобы контакты и реквизиты не
    терялись и не смешивались с основным содержимым.

## Locator v0.1

Locator строится детерминированно:

```text
head/title
header/p[1]
body/h1[1]
body/p[3]
body/li[2]
body/table[1]/row[2]/cell[1]
body/a[4]
footer/p[1]
```

Promotion отклоняется, если locator отсутствует или цитата не содержится в
соответствующем блоке.

## SR-G1 fixtures

`tests/fixtures/input-stabilization-encodings.json` фиксирует Windows-1251,
UTF-8, UTF-8 BOM и detector path. `tests/fixtures/cms-multi-area.html`
фиксирует Tilda/Bitrix-подобную страницу с несколькими смысловыми областями,
header, юридическим блоком и footer. SPA fallback продолжает проверяться
отдельным dynamic fixture.

## Crawl4AI worker

Адаптер использует self-hosted REST `POST /crawl` с `urls`,
`BrowserConfig` и `CrawlerRunConfig`. Конфигурация:

```text
CRAWL4AI_BASE_URL=http://crawl4ai:11235
CRAWL4AI_API_TOKEN=...
```

Для stage/production:

- worker должен быть отдельным контейнером во внутренней сети;
- image необходимо закрепить на проверенной версии, не использовать `latest`;
- допускается Crawl4AI не ниже `0.8.9`, поскольку эта линия закрывает известные
  SSRF-дефекты Docker API; целевая проверяемая версия — `0.9.2`;
- API token обязателен;
- CPU/RAM, egress, concurrency и restart policy задаются инфраструктурой.

Официальная документация:

- <https://docs.crawl4ai.com/core/self-hosting/>
- <https://github.com/unclecode/crawl4ai/blob/main/CHANGELOG.md>

## Benchmark-5

Исполняемый набор:

```text
benchmarks/sef/document-fetch-5-v0.1.json
scripts/run_document_fetch_benchmark.py
tests/test_document_pipeline.py
```

Шлюз: не менее `80%` разрешённых HTML-документов извлекаются без ручного
копирования. Текущий fixture-run: `5/5`.

## Граница P0

P0 использует memory cache и не заявляет сохранность после restart. Следующий
инкремент должен сохранить raw object, document metadata, version и idempotency
key в PostgreSQL/object storage без изменения этого прикладного контракта.
