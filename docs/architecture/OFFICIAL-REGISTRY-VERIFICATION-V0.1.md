# Official Registry Verification v0.1

## Назначение

Срез продолжает SA-SR-03 (#84) после provisional identity, Evidence Guard и Identity Benchmark-5. Он вводит fail-closed проверку уже загруженного официального реестрового документа и типизированную передачу неоднозначного решения человеку.

## Граница ответственности

`OfficialRegistryVerifier` не выполняет сетевой запрос самостоятельно. Внешний connector обязан:

1. получить официальный документ ЕГРЮЛ/ЕГРИП;
2. сохранить документ и digest;
3. сформировать `RegistryEvidence` с authority, URL, locator и временем доступа;
4. только затем вызвать verifier.

Так snippet, поисковая выдача или неподтверждённый API-ответ не могут стать accepted identity link.

## Автоматическое подтверждение

Состояние `verified` допустимо только когда:

- присутствует запись с ролью `subject`;
- совпадает хотя бы один сильный идентификатор — ИНН или ОГРН/ОГРНИП;
- отсутствуют расхождения сильных идентификаторов;
- нормализованное юридическое наименование не конфликтует;
- запись филиала, бренда, владельца или аффилированной компании не подменяет исследуемый субъект.

Accepted identifier link получает детерминированный идентификатор, связанный с candidate, scheme, value, evidence id и locator.

## Human review

`HumanReviewRequest` создаётся при:

- несовпадении ИНН, ОГРН/ОГРНИП или юридического наименования;
- нескольких различных subject records;
- нескольких authorities в одном решении;
- наличии branch/brand/owner/affiliate evidence;
- отсутствии subject record.

Разрешённые решения: `accept`, `reject`, `request_more_evidence`. До решения accepted links не создаются, а client release остаётся закрыт.

## Следующий интеграционный шаг

Следующий PR должен подключить реальный connector официального реестра к Mission Orchestrator:

`official_registry_verification → fetch authoritative document → RegistryEvidence → OfficialRegistryVerifier → promote_identifier_links(authority_verified=true)`.

Сетевой connector, хранение review decision и REST/MCP endpoints в этот ограниченный срез не входят.
