# SA-SEF-06 — Human Review и Report v1

## Назначение

Report v1 превращает доказательный Company Profile v1 в выпускаемый клиентский
артефакт. Выпуск разрешается только после явного решения человека, привязанного к
точному snapshot профиля и приложения доказательств.

## Двухшаговый протокол

1. `POST /api/sef/report/review-package` пересчитывает Claim & Evidence Ledger и
   Company Profile v1, затем возвращает:
   - полный профиль для проверки;
   - `profile_digest`;
   - `evidence_appendix_digest`;
   - `reviewable` и список блокеров.
2. Рецензент проверяет этот пакет и передаёт оба digest в
   `POST /api/sef/report` или `POST /api/sef/report.html` вместе с решением,
   временем, основанием и attestation.

Клиент не передаёт Ledger snapshot, готовый профиль, Report ID,
`client_release_ready` или итоговый digest. Сервис вычисляет их самостоятельно.

## Шлюз выпуска

Report создаётся только если одновременно выполнены условия:

- все шесть критических пробелов Company Profile закрыты;
- отсутствуют неразрешённые конфликты;
- в профиле нет hypothesis, blocked или `not_found` полей;
- приложение доказательств не пусто;
- решение человека равно `approved`;
- attestation явно установлен;
- оба подписанных digest совпадают с пересчитанным snapshot;
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
- блок целостности и `client_release_ready=true`.

## Канонизация и смысл «подписи»

Digest вычисляются как SHA-256 от UTF-8 JSON с сортировкой ключей и компактными
разделителями (`json-sort-keys-utf8-v1`). Human sign-off является
аудиторской фиксацией личности рецензента, решения, времени, основания и
проверенных digest. Это не квалифицированная электронная подпись и не заменяет
КЭП. Криптографическая PDF-подпись и PKI находятся вне P0.

## HTML export

`POST /api/sef/report.html` возвращает печатное HTML-представление того же
проверенного Report v1. Все значения из профиля и доказательств HTML-экранируются.
Поисковые snippets не входят в Company Profile и потому не могут попасть ни в
JSON, ни в HTML.

## Не входит в P0

- очередь рецензентов, RBAC и UI;
- долговременное хранилище версий;
- PDF с КЭП и XLSX;
- автоматическое разрешение конфликтов;
- batch/hunt.
