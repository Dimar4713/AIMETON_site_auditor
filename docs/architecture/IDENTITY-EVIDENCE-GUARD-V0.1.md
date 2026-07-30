# AIMETON Identity Search & Evidence Guard v0.1

**Статус:** candidate-срез `SA-SR-03 / #84`, подготовленный после добавления
repository secret `TAVILY_TOKEN`. До merge, зелёного CI, Deploy Stage и live
read-back этот документ описывает проверенный локально кандидат, а не факт
stage.

## Назначение

Срез связывает provisional identity с реальным поиском и первичным документом:

```text
provisional IdentityResolutionResult
  → issued query_provider plan
  → Tavily Basic / Provider Gateway
  → ProviderCall + DiscoveryHint
  → issued fetch_document plan
  → Document Pipeline
  → Evidence Guard
  → Evidence + EntityIdentifier
  → новая identity revision с accepted_identifier_links
  → targeted crawl candidate
```

Tavily не является источником identity-факта. Его ответ и snippet всегда
остаются `DiscoveryHint`. Evidence создаётся только из отдельно загруженного
документа.

## API

```http
POST /api/missions/{mission_id}/identity-search
POST /api/missions/{mission_id}/identity-evidence
```

Первый endpoint принимает выданный `query_provider` plan и ID текущей identity
revision. Он исполняет только action, который присутствовал в
`next_action_candidates` этой ревизии.

Второй endpoint принимает отдельный выданный `fetch_document` plan, ID
предыдущего search result и ID identity revision. URL должен одновременно:

- происходить из сохранённого `DiscoveryHint`;
- присутствовать в `next_action_candidates` search result;
- пройти Mission Orchestrator и domain policy;
- пройти SSRF/redirect/content-size проверки Document Pipeline.

Оба исполнения идемпотентны по `mission_id + turn_number`; повтор с другим
входом отклоняется.

## Tavily: стоимость и пределы

По официальной документации Tavily на дату реализации:

- Basic Search расходует 1 API credit;
- бесплатный Researcher-план предоставляет 1000 credits в месяц;
- верхняя pay-as-you-go оценка — `$0.008` за credit.

Источники:

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Credits & Pricing](https://docs.tavily.com/documentation/api-credits)

Identity-контур использует:

- `search_depth=basic`;
- `include_answer=false`;
- `include_raw_content=false`;
- `retries=0`;
- оценку `$0.008` на запрос;
- явный mission budget;
- process-local quota;
- отдельный порядок `IDENTITY_SEARCH_PROVIDER_ORDER=tavily,searxng`.

Наличие токена не отменяет бюджетный шлюз. Если стоимость, бюджет или quota не
заданы, Provider Gateway блокирует вызов.

## Evidence Guard

Автоматическое принятие identity link возможно только при одновременном
выполнении условий:

1. документ фактически загружен и имеет URL, `accessed_at`, raw и normalized
   digest;
2. источник — same-domain first-party либо allowlisted официальный реестр;
3. юридическое наименование выбранного кандидата присутствует в документе;
4. ИНН или ОГРН найден рядом с явной меткой в извлечённом блоке;
5. контрольный разряд реквизита корректен;
6. реквизит совпадает с provisional candidate;
7. документ не содержит другой валидный ИНН/ОГРН той же схемы;
8. evidence создаётся через проверяемый locator и quote.

Любой разрыв создаёт `guard_state=blocked`; ни один identifier из документа
тогда не принимается. Это защищает от карточек-каталогов и автоматического
слияния «Дедал» с «Дедал Плюс».

## Состояние после принятия

Для first-party документа:

- `accepted_identifier_links` получают ID доказанных `EntityIdentifier`;
- история получает append-only revision с `supersedes_result_id`;
- identity остаётся `provisional`;
- сохраняется дефицит `official_registry_verification`;
- разрешается typed `targeted_company_profile` crawl;
- отдельный registry-query остаётся кандидатом.

Для allowlisted официального реестра question `identity` может стать
`verified`, но различение бренда, филиала, владельца и аффилированной компании
остаётся отдельной задачей.

## Секрет и stage

Каноническое имя GitHub secret — `TAVILY_TOKEN`; legacy
`TAVILY_API_KEY` поддерживается runtime только как обратная совместимость.
Deploy Stage:

1. получает secret через GitHub Actions environment;
2. проверяет его наличие без чтения значения в лог;
3. атомарно создаёт на сервере отдельный файл с правами `0600`;
4. подключает файл через Docker Compose override;
5. не включает secret в source bundle, artifacts, health или diagnostics.

## Границы v0.1

- состояние mission/search/history process-local;
- HTML поддержан текущим Document Pipeline; PDF/DOCX относится к следующему
  срезу `#85`;
- quota process-local и сбрасывается при restart;
- stage факт будет зафиксирован только после deployment и live-cycle;
- официальный registry connector, human review и Benchmark identity остаются
  открытыми частями `#84`.

## Проверка

```bash
python scripts/export_identity_evidence_schemas.py
pytest -q tests/test_identity_evidence.py
pytest -q
bash -n scripts/deploy_stage.sh
```

Целевые тесты подтверждают:

- snippet не создаёт accepted link;
- один Tavily Basic call учитывает `$0.008`;
- first-party документ создаёт locator-bound evidence;
- competing валидный ИНН блокирует всю promotion;
- повтор action не создаёт вторую ревизию;
- committed JSON Schemas совпадают с моделями.
