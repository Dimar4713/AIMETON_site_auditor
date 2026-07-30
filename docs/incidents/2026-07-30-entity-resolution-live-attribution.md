# Incident: ложный identity conflict на реальных страницах реквизитов

Дата обнаружения: 2026-07-30  
Статус: исправлено и подтверждено на stage
Связанная задача: `#84`

## Фактическое состояние

Stage `0.16.0 / 1ed2376ab589b1174da29998cfbda7fdb4ede127` успешно получил
`TAVILY_TOKEN`; Tavily был operationally ready. Перед первым платным вызовом
fail-closed Entity Resolution проверен на first-party страницах Selectel,
Sendy и БСК.

Во всех трёх случаях resolver вернул `conflicting` и не создал
`selected_candidate_id`. Tavily не вызывался, кредит не расходован.

## Причина

Проблема состояла из четырёх независимых эффектов:

1. legal-name regex захватывал descriptive tail после имени в title/H1;
2. полная/сокращённая правовая форма и разные кавычки давали разные anchors;
3. банковские контрагенты считались равноправными target-субъектами страницы;
4. метка `адрес` совпадала с началом слова `адреса` и создавала ложные
   address signals.

Дополнительно label и value в соседних HTML-блоках/табличных ячейках не всегда
извлекались как единый provenance-bearing signal.

## Решение `0.16.1`

- legal name ограничивается закрывающей кавычкой или границей bare-name;
- полные формы `ООО/АО/ПАО/ЗАО` канонизируются с сокращёнными;
- соседние `label → value` блоки дают сигнал с составным locator;
- bank-like имя становится вторичным только при наличии иного небанковского
  субъекта в том же документе;
- сильные идентификаторы автоматически связываются лишь с единственным
  небанковским target;
- слабые сигналы не копируются во все кандидаты документа;
- два небанковских имени или разные сильные реквизиты сохраняют fail-closed
  conflict;
- address regex требует полную метку и явный разделитель.

## Regression evidence

В репозитории добавлены три минимизированных sanitized fixture, сохраняющих
структурные особенности обнаруженных страниц:

- `realworld_selectel_sanitized.html`;
- `realworld_sendy_sanitized.html`;
- `realworld_bsk_sanitized.html`.

Интеграционный тест проходит путь `HTML extraction → bootstrap signals →
provisional resolution` и проверяет target name, ИНН, ОГРН и отсутствие
ложного address fragment. Фактические CI, deployment и live evidence
зафиксированы ниже.

## Deployment и live evidence

- implementation PR: `#102`;
- merge/deployment SHA:
  `5d7cb748f95868b92871aaa6fbce842c29f93ea9`;
- PR Baseline CI: `#30521337143` — success;
- main Baseline CI: `#30521415347` — success;
- Deploy Stage: `#30521495457` — success;
- stage read-back: `version=0.16.1`, exact deployment SHA;
- Tavily и SearXNG: active; secrets не экспонируются.

Повторный live-цикл использовал first-party страницу БСК:

1. bootstrap завершён;
2. resolver выбрал provisional ООО «Анатомика» с ИНН `2308284006` и ОГРН
   `1222300007225`;
3. Tavily Basic вызван ровно один раз (`quota 10 → 9`), но usable results не
   вернул;
4. бесплатный SearXNG fallback сформировал пять discovery hints;
5. продолжение той же поисковой сигнатуры из cache стоило `$0`;
6. `bsckrd.ru/requisites` загружен как first-party document;
7. Evidence Guard принял ИНН и ОГРН с locator `footer/li[5]` и `footer/li[6]`;
8. identity history содержит две ревизии, targeted crawl candidate создан;
9. `official_registry_verification` остаётся открытым дефицитом.

Таким образом, P0-дефект attribution устранён. Tavily delivery и budget
подтверждены, но его search quality на данном сложном identity query не
подтверждена: полезный документ в этом smoke найден через SearXNG fallback.
