# SA-SR-G2 — исполнимый план Entity Resolution

Статус: active critical path  
Управляющие Issue: #66, #80, #84  
Предшествующий gate: #145/#203 завершён, ограниченный stage MVP принят.

## Цель

Закрыть оставшиеся критерии #84 и доказать, что AIMETON не смешивает факты разных юридических субъектов, сохраняет конкурирующих кандидатов и fail-closed блокирует клиентский выпуск при неразрешённой идентичности.

## Каноническая граница

Entity Resolution не создаёт факты и не заменяет Evidence Guard. Он принимает только identity signals с document id, URL, locator, accessed_at и digest, формирует кандидатов и конфликты и возвращает typed feedback в Mission Orchestrator.

## Критический путь

```text
ER-1 competing candidates/history
  → ER-2 legal-form and strong-identifier conflict policy
  → ER-3 typed identity_unresolved + search deficit
  → ER-4 Report Gate integration
  → ER-5 Dedal/Slavdom regression evidence
  → #86 Sufficiency feedback loop
```

## ER-1 — сохранение competing candidates

Результат:

- все подтверждённые strong-anchor группы (`INN`, `OGRN/OGRNIP`, legal name + provenance) остаются в `candidates`;
- выбор одного кандидата не удаляет и не перезаписывает остальные;
- новая revision содержит `supersedes_result_id`, монотонный `revision_number` и полную историю ранее обнаруженных кандидатов;
- одинаковый вход даёт воспроизводимые candidate IDs и ordering.

Acceptance:

- два юридических субъекта в одном наборе документов дают не менее двух candidates;
- competing candidate остаётся доступным после появления authoritative evidence для выбранного кандидата;
- история не содержит cross-mission данных.

## ER-2 — запрет ложного объединения ИП и ООО

Политика:

- совпадение бренда, телефона, адреса или домена само по себе не объединяет разные legal forms;
- ИНН/ОГРН/ОГРНИП являются strong identifiers и не могут быть усреднены;
- `sole_proprietor` и `company` объединяются только при явном relation evidence, но остаются разными identity candidates;
- противоречащие strong identifiers создают `IdentityConflict` и требуют review/targeted search.

Контрольный сценарий:

- исследуемый субъект «Дедал» не объединяется с ООО «Дедал Плюс» без документа и locator, явно доказывающих отношение;
- факты ООО не становятся фактами ИП и наоборот.

## ER-3 — typed identity_unresolved

`IdentityResolutionResult.state = unresolved`, когда:

- нет валидного strong anchor;
- competing candidates не могут быть разрешены допустимым evidence;
- документ неоднозначно приписывает реквизиты нескольким legal names;
- критический identity conflict остаётся открытым.

Обязательный feedback:

- `gaps` содержит конкретные недостающие связующие доказательства;
- `recommended_feedback` снижает `identity_resolution` и создаёт явный deficit;
- `next_action_candidates` содержит только допустимые targeted actions;
- unresolved не маскируется как provisional/completed.

## ER-4 — Report Gate

- `identity_unresolved` и unresolved strong conflict физически запрещают client report release;
- внутренний технический результат сохраняется;
- UI/API возвращают typed reason без raw documents, secrets и внутренних трасс;
- высокий coverage второстепенных данных не компенсирует identity gap.

## ER-5 — независимая регрессия

### dedal24.ru

Проверить:

- competing identity candidates;
- ИП/ООО separation;
- отсутствие cross-company claims;
- provenance каждого accepted identifier;
- unresolved/conflict блокирует release.

### slavdom24.ru

Проверить:

- legal identity либо доказанный `identity_unresolved`;
- контакты/филиалы не создают ложное legal merge;
- evidence остаётся owner-scoped и sanitized.

## Разбиение на PR

1. **ER-1 PR** — regression contracts для candidate preservation и deterministic history.
2. **ER-2 PR** — legal-form/strong-identifier conflict policy и Dedal fixture.
3. **ER-3 PR** — unresolved deficit + Report Gate integration.
4. **ER-4 PR** — independent cost-bounded stage acceptance для dedal24.ru/slavdom24.ru.

Каждый PR:

- `Part of #84`;
- содержит `## Acceptance criteria affected`;
- проходит Acceptance Governance, Project Status Sync и Baseline CI;
- не включает платные provider-вызовы без отдельного budget decision;
- не меняет OCC-49, архитектурные инварианты, юридические обязательства или production.

## Exit gate #84

- [ ] 0 фактов другой компании в контрольном наборе;
- [ ] «Дедал» не объединён с ООО «Дедал Плюс» без relation evidence;
- [ ] competing candidates не затираются;
- [ ] `identity_unresolved` создаёт search deficit;
- [ ] Report Gate блокирует client release;
- [ ] unit/integration regression зелёная;
- [ ] independent stage verdict опубликован.

## Следующий критический шаг

Открыть ER-1 delivery PR: добавить детерминированные regression tests для сохранения competing candidates и revision history на текущем `ProvisionalEntityResolver`, затем исправлять только подтверждённые тестами дефекты.