# SA-SEF-06 — Human Review и Report v1

## Назначение

Report v1 превращает доказательный Company Profile v1 в выпускаемый клиентский
артефакт. Начиная с контракта `1.1.0` выпуск разрешается только после явного
решения человека, привязанного к точным snapshot профиля, приложения
доказательств и `MissionReleaseControl`.

`MissionReleaseControl` введён в SA-SR-00 как немедленная fail-closed граница.
Он не подменяет будущие Mission Orchestrator и УДП Evaluator: задачи #83 и #86
должны вычислять и сохранять его значения из фактического исполнения миссии.

## Двухшаговый протокол

1. `POST /api/sef/report/review-package` пересчитывает Claim & Evidence Ledger и
   Company Profile v1, затем возвращает:
   - полный профиль для проверки;
   - `profile_digest`;
   - `evidence_appendix_digest`;
   - фактические УДП, identity, execution integrity, обязательные вертикали,
     providers, budget и раздельные метрики;
   - `release_control_digest`;
   - `reviewable` и список блокеров.
2. Рецензент проверяет этот пакет и передаёт три digest в
   `POST /api/sef/report`, `POST /api/sef/report.html`,
   `POST /api/sef/report.md` или `POST /api/sef/report.docx` вместе с решением,
   временем, основанием и attestation.

Клиент не передаёт Ledger snapshot, готовый профиль, Report ID,
`client_release_ready` или итоговый digest. Сервис вычисляет их самостоятельно.
`release_control` является серверным snapshot состояния миссии. Пока #83/#86 не
стали его авторитетным производителем, отсутствие этого объекта закрывает
Report Gate по умолчанию.

Минимальный состав `MissionReleaseControl`:

- `target_sufficiency` и `achieved_sufficiency`;
- `identity_state`;
- `execution_integrity` и `analysis_state`;
- число неразрешённых критических конфликтов;
- состояния обязательных вертикалей и providers;
- состояние бюджета;
- отдельные `profile_completeness`, `evidence_quality` и
  `commercial_priority`;
- время оценки и типизированные reason codes.

## Шлюз выпуска

Report создаётся только если одновременно выполнены условия:

- все шесть критических пробелов Company Profile закрыты;
- отсутствуют неразрешённые конфликты;
- `execution_integrity=validated`;
- `analysis_state=schema_validated`; эвристический fallback имеет только
  `preliminary_hypothesis`;
- `identity_state=resolved`;
- целевой и достигнутый УДП не ниже L4, достигнутый уровень не ниже целевого;
- каждая обязательная вертикаль имеет `verified` или
  `not_found_after_sufficient_search`;
- каждый обязательный provider имеет состояние `active`;
- `budget_state=within_budget`;
- в профиле нет hypothesis, blocked или `not_found` полей;
- приложение доказательств не пусто;
- решение человека равно `approved`;
- attestation явно установлен;
- все три подписанных digest совпадают с пересчитанным snapshot;
- решение принято не раньше snapshot и не позже формирования отчёта;
- время формирования отчёта не предшествует snapshot.

При нарушении шлюза API возвращает `409 report_release_blocked` и стабильные
reason codes. Заблокированный результат не выдаётся как клиентский отчёт.

## Состав Report v1

- неизменяемые `id`, `version` и `report_content_digest`;
- идентификаторы mission, entity, correlation и Company Profile;
- только verified и client-eligible claims;
- 14 секций профиля с отфильтрованными полями;
- оценки шести критических пробелов;
- evidence appendix с URL, цитатой, locator, document/evidence digest и связями
  с claims;
- human sign-off с отдельным digest;
- `release_control_digest`, блок целостности и
  `client_release_ready=true`;
- раздельные УДП, полнота профиля, качество evidence и коммерческий
  приоритет.

## Канонизация и смысл «подписи»

Digest вычисляются как SHA-256 от UTF-8 JSON с сортировкой ключей и компактными
разделителями (`json-sort-keys-utf8-v1`). Human sign-off является
аудиторской фиксацией личности рецензента, решения, времени, основания и
проверенных digest. Это не квалифицированная электронная подпись и не заменяет
КЭП. Криптографическая PDF-подпись и PKI находятся вне P0.

## Форматы экспорта

`POST /api/sef/report.html` возвращает печатное HTML-представление того же
проверенного Report v1. Все значения из профиля и доказательств HTML-экранируются.
Поисковые snippets не входят в Company Profile и потому не могут попасть ни в
JSON, ни в HTML.

`POST /api/sef/report.md` возвращает структурированный Markdown, а
`POST /api/sef/report.docx` — нативный редактируемый Word-документ. Оба формата
содержат Report ID, human sign-off, evidence appendix и все digest целостности.
Они строятся только из заново пересчитанного и выпущенного Report v1 и
наследуют тот же fail-closed шлюз.

Для исследовательского результата до human review доступны отдельные
`POST /api/export/analysis.md` и `POST /api/export/analysis.docx`. Такие файлы
имеют явную маркировку «предварительный анализ», не содержат
`client_release_ready=true` и никогда не включают диалог с консультантом.
Предварительный JSON/MD/DOCX также показывает `analysis_state`, УДП, identity,
полноту профиля, качество evidence, коммерческий приоритет, budget и блокеры.
Успешная schema-validation LLM не превращает одностраничный анализ в клиентский
Report v1.
Формат старого Word `.doc` не создаётся: используется современный открытый
формат `.docx`.

## Не входит в P0

- очередь рецензентов, RBAC и UI;
- долговременное хранилище версий;
- PDF с КЭП, бинарный `.doc` и XLSX;
- автоматическое разрешение конфликтов;
- batch/hunt.
