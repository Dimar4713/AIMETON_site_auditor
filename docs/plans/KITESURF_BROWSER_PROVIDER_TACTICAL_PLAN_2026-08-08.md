# Kitesurf Browser Provider — тактический план интеграции в AIMETON Site Auditor

Дата: 2026-08-08
Статус: approved for experimental spike; production routing unchanged.

## 1. Цель

Проверить, способен ли Cloudflare Kitesurf стать промежуточным web-rendering provider между static HTTP fetch и тяжёлым Playwright/Chromium, снизив вычислительную стоимость массового анализа без ухудшения качества Evidence и Company Intelligence.

## 2. Текущая точка интеграции

В Site Auditor уже есть capability boundary `app/capabilities/web_rendering/` и resolver с каскадом static fetch → Playwright → Chromium CLI.

Целевой экспериментальный маршрут:

```text
httpx/static
  ↓ dynamic/insufficient
kitesurf (experimental, feature-flagged)
  ↓ incompatible / insufficient / policy deny
playwright
  ↓ failure
chromium-cli
```

Kitesurf не заменяет существующие providers и не становится hard dependency.

## 3. Изменения контракта

Разрешить provider identifier `kitesurf` в `RenderedPage` после реализации provider.

Новый provider обязан возвращать тот же минимальный контракт:

- final_url;
- title;
- text;
- provider=`kitesurf`;
- html_bytes;
- валидный HTTP/HTTPS URL;
- непустой извлечённый текст либо контролируемый `FetchError`.

Доменные и downstream-компоненты не должны знать Cloudflare-specific API.

## 4. Feature flags и kill switch

Предлагаемые настройки:

```text
AIMETON_KITESURF_ENABLED=false
AIMETON_KITESURF_ENDPOINT=
AIMETON_KITESURF_TIMEOUT_S=20
AIMETON_KITESURF_MAX_ATTEMPTS=1
AIMETON_KITESURF_ALLOW_AUTH=false
AIMETON_KITESURF_RECORDING=false
```

Требования:

- default OFF;
- отсутствие переменных/секретов не ломает сервис;
- выключение флага мгновенно восстанавливает старый resolver path;
- секреты никогда не попадают в логи/evidence.

## 5. Data policy guard

До отдельного решения provider разрешён только для публичного Web.

Policy deny для:

- authenticated customer sessions;
- admin panels;
- customer-private resources;
- страниц, куда передаются секреты/token/cookies;
- внутренних AIMETON endpoints.

При deny resolver обязан продолжить локальным/штатным provider, а не завершать миссию ошибкой.

## 6. Реализация spike

### KSF-T1 — provider adapter

Создать `app/capabilities/web_rendering/kitesurf_fetcher.py`.

Обязанности адаптера:

- подключение к Kitesurf/Browser Run через поддерживаемый endpoint/CDP path;
- navigation timeout;
- получение final URL/title/visible text/HTML size;
- нормализация ошибок в `FetchError`;
- отсутствие Cloudflare-specific типов выше capability layer.

### KSF-T2 — resolver integration

Добавить Kitesurf после static HTTP и перед Playwright только при `AIMETON_KITESURF_ENABLED=true` и успешном policy check.

Fallback должен быть гарантированным:

```text
Kitesurf error → Playwright
Playwright error → Chromium CLI
```

### KSF-T3 — observability

Для каждого вызова фиксировать без секретов:

- selected_provider;
- selection_reason;
- started_at/finished_at;
- latency_ms;
- success/failure;
- failure_class;
- html_bytes/text_length;
- fallback_provider;
- policy_decision;
- estimated/actual provider cost при наличии данных.

Эти события должны быть связаны с mission/runtime evidence.

### KSF-T4 — tests

Добавить unit/integration tests:

1. feature flag OFF — старое поведение без изменений;
2. successful Kitesurf result;
3. Kitesurf timeout → Playwright;
4. Kitesurf malformed/empty result → Playwright;
5. policy deny → Playwright/local provider;
6. Kitesurf+Playwright fail → Chromium CLI;
7. provider validation принимает `kitesurf` только после изменения контракта;
8. отсутствие credentials не ломает baseline CI.

## 7. Benchmark corpus

Сформировать 50–100 реальных публичных SMB-сайтов из приоритетных для AIMETON сегментов:

- стоматологии и клиники;
- строительство;
- производство;
- логистика;
- юридические/B2B услуги;
- интернет-магазины;
- локальные сервисные компании.

Для каждого URL прогнать сопоставимые сценарии через:

- HTTPX/static;
- Kitesurf;
- Playwright/Chromium.

## 8. Метрики

Обязательные:

- navigation/render success rate;
- extracted text completeness;
- contacts/links extraction completeness;
- JS-generated content coverage;
- DOM/accessibility usefulness при наличии;
- screenshot fidelity для UI-audit subset;
- latency p50/p95;
- CPU/RAM или provider browser time там, где измеримо;
- cost per successful page;
- fallback rate;
- downstream Company Intelligence completeness;
- evidence loss/regression rate.

## 9. Критерии Go / No-Go

### GO в штатный L1 provider

Только если одновременно:

- нет значимой регрессии downstream quality;
- fallback надёжен;
- data policy выполняется;
- provider может быть отключён без изменения кода домена;
- стоимость/масштабирование подтверждены evidence;
- Kitesurf снимает существенную долю тяжёлых browser calls; рабочий ориентир 60–70% dynamic cases, ранее требовавших Chromium.

### NO-GO / оставить experimental

Если:

- высокая несовместимость целевых сайтов;
- ухудшается extraction/evidence quality;
- стоимость после beta непредсказуема/невыгодна;
- не удаётся обеспечить data isolation policy;
- provider создаёт hard dependency или нестабильный production path.

## 10. Приоритет относительно текущего продукта

Spike не должен вытеснять критические задачи качества действующего Site Auditor.

Приоритет:

1. сохранять работоспособность stage/production;
2. не ломать текущий resolver;
3. выполнить эксперимент изолированно;
4. использовать результат для ускорения Hunter и Company Intelligence;
5. включать штатно только после evidence-based acceptance.

## 11. Связь с продуктовой стратегией

Для направления быстрых денег Kitesurf ценен не сам по себе, а как способ снизить стоимость первичной разведки большого количества потенциальных клиентов. Глубокий Chromium/LLM-анализ должен тратиться на меньшую, более качественно отобранную выборку.

Целевая логика Hunter:

```text
search/discovery
  ↓
cheap static acquisition
  ↓
Kitesurf dynamic acquisition
  ↓
qualification
  ↓
full browser + deep intelligence only for promising targets
```

## 12. Definition of Done для spike

Spike завершён только когда:

- provider реализован за capability contract;
- baseline tests зелёные;
- production default остаётся OFF;
- benchmark выполнен;
- evidence сохранён;
- сформирован Go/No-Go вывод;
- roadmap обновлён фактическими результатами, а не рекламными заявлениями поставщика.
