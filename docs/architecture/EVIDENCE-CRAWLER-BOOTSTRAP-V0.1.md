# AIMETON Evidence Crawler — Bootstrap v0.1

Статус: candidate-срез `SA-SR-04 / #85` в ветке
`agent/sa-sr-04-evidence-crawler-bootstrap`. До merge, зелёного CI и stage
read-back не является эксплуатационным фактом. Полная `#85` этим срезом не
закрывается.

## Назначение

Bootstrap capability исполняет первый допустимый `crawl_url` plan Mission
Orchestrator:

```text
issued plan
  → robots + sitemap
  → bounded same-domain HTML fetch
  → blocks/locators/digests/links
  → identity candidates + primary-document hints
  → ActionOutcome + next ActionCandidates
```

Он не разрешает идентичность, не вычисляет УДП и не превращает найденный текст
в Evidence. Результат предназначен для последующих `#84`, `#86` и `#87`.

## Исполняемый контракт

Вход:

- существующий `mission_id`;
- последний выданный `NextActionPlan` с выбранным `crawl_url`;
- `BootstrapCrawlPolicy`.

API:

```http
POST /api/missions/{mission_id}/bootstrap-crawl
```

Повтор того же `(mission_id, turn_number)` до записи outcome идемпотентен.
Конкурирующее исполнение того же plan отклоняется. Одновременно в процессе
выполняются не более двух bootstrap runs.

Выход `BootstrapCrawlResult` содержит:

- связь `mission_id / analysis_id / correlation_id`;
- состояние robots и обработанные sitemap URL;
- страницы с requested/final URL, depth, page type, document ID,
  raw/normalized digest;
- identity signals с document ID и locator;
- ссылки на первичные документы с исходным документом и locator;
- blocked/failed/discovered URL;
- `ActionOutcome` и типизированные candidates следующего шага.

## Policy и безопасность

До и во время исполнения действуют:

- только issued plan этого Mission Orchestrator;
- target внутри host family миссии (`host` и `www.host`);
- SSRF validation до каждого HTTP/redirect hop;
- строгий domain allowlist до redirect, а не post factum;
- robots longest-match, включая `*` и terminal `$`;
- при недоступном robots — fail closed;
- bounded pages, depth, sitemap count/URL count, bytes, deadline и links;
- последовательные запросы внутри run и interval между всеми попытками;
- URL dedupe не объединяет разные schemes, hosts или paths;
- discovered URL с query не ставятся в queue и не выводятся как document hint;
- нестандартный port требует точного `host:port` в domain allowlist;
- process-wide concurrency не выше двух runs.

Строгий bootstrap не использует dynamic worker: при активном domain allowlist
динамический fallback закрыт, пока worker не сможет доказуемо соблюдать ту же
redirect/domain policy. HTTP остаётся первым и единственным разрешённым путём
этого среза.

## Evidence boundary

Детерминированно извлекаются только identity **candidates**:

- ИНН;
- ОГРН/ОГРНИП;
- телефоны;
- email;
- адрес;
- наименование юридического лица.

Каждый signal связан с документом, URL и locator, но не является accepted
identity link или Evidence. PDF/DOC/DOCX/XLS/XLSX ссылки сохраняются как
`discovery_hint`; `fetch_document` предлагается только для same-domain URL.
Внешняя ссылка остаётся наблюдаемым hint и не открывается bootstrap crawler.

## Проверяемый оборот

Контрольный fixture доказывает:

1. root, contacts и about получены из root/sitemap;
2. более специфичный `Disallow: /private` побеждает `Allow: /`;
3. запрещённая страница не запрашивается;
4. INN/OGRN/phone/email/address/legal name имеют locators;
5. same-domain PDF порождает `fetch_document`, внешний PDF — только hint;
6. outcome записывается в turn 1;
7. следующий plan выбирает `resolve_identity` как turn 2;
8. другая mission не может исполнить или прочитать этот plan.

## Не входит

- accepted Entity Resolution (`#84`);
- targeted crawl по дефициту УДП;
- загрузка и извлечение PDF/DOCX;
- AI-анализ каждой страницы/пакета и разрешение конфликтов (`#87`);
- канонический SufficiencyDelta/stop decision (`#86`);
- durable checkpoints/restart recovery (`#88`);
- incident sites и Benchmark-5 acceptance.
