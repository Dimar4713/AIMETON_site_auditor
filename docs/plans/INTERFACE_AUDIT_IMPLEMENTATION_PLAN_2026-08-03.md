# План внедрения Interface Audit Capability

**Дата:** 2026-08-03  
**Статус:** принят к реализации  
**Архитектура:** `docs/architecture/INTERFACE_AUDIT_CAPABILITY_V0.1.md`

## 1. Целевой результат

Получить минимально исполнимую и доказательную capability, которая:

1. открывает реальный интерфейс в Chromium;
2. собирает runtime artifacts;
3. проверяет основной пользовательский flow;
4. применяет версионированный AIMETON rule pack;
5. формирует до пяти приоритетных root-cause findings;
6. явно показывает coverage, rejected candidates и verification gaps;
7. выдаёт `block`, `needs_changes`, `approve` или `inconclusive`;
8. используется сначала на stage-интерфейсе AIMETON, затем как клиентская услуга.

## 2. Принципы реализации

- не создавать второй browser stack;
- расширять существующий `app/capabilities/web_rendering`;
- сохранять artifacts отдельно от summary JSON;
- все выводы связывать с evidence;
- не блокировать CI по неподтверждённой эвристике;
- read-only по умолчанию;
- фиксировать rule pack version и upstream provenance;
- реализовывать вертикальными срезами, каждый из которых можно проверить на stage.

## 3. Этап IA-00 — provenance и rule pack skeleton

### Работы

- зафиксировать upstream `jakubkrehel/skills`;
- зафиксировать fork `Dimar4713/skills`;
- записать snapshot `a67333399dabbc71d7778962cb9c4fb9b86a00d0`;
- сохранить MIT attribution;
- создать локальный каталог rule pack;
- ввести `rule_id`, `rule_version`, `authority`, `source`;
- адаптировать первые правила Accessibility, Layout, Writing и Observability.

### Acceptance

- production не читает upstream/fork во время миссии;
- один и тот же rule pack воспроизводимо загружается по версии;
- каждый adapted rule содержит provenance;
- heuristics отделены от обязательных gates.

## 4. Этап IA-01 — Interface Evidence Collector

### Работы

Расширить Playwright-сборщик:

- screenshot текущего viewport;
- full-page screenshot;
- DOM snapshot;
- page URL/title/language;
- console messages;
- page errors;
- failed network requests;
- navigation redirects;
- viewport/theme/reduced-motion metadata;
- artifact digest;
- timeout/cancellation/size limits.

### Предлагаемые файлы

```text
app/capabilities/interface_audit/evidence_collector.py
app/capabilities/interface_audit/contract.py
app/capabilities/interface_audit/passport.yaml
```

### Acceptance

- collector работает на статической и JavaScript-странице;
- artifacts имеют stable refs и SHA-256 digest;
- SSRF guard остаётся активным;
- secrets не попадают в console/network artifacts;
- отменённая миссия освобождает browser/context;
- есть unit и integration tests.

## 5. Этап IA-02 — Quick Audit Orchestrator

### Работы

- scope resolver;
- режим `quick`;
- desktop + narrow viewport;
- primary flow без destructive actions;
- domain reviewers: Accessibility, Layout, Writing, Observability;
- structured findings;
- finding cap = 5;
- root-cause consolidation;
- `considered_rejected`;
- `not_verified`;
- verdict.

### Acceptance

- каждая находка имеет evidence ref и locator;
- повторяющиеся DOM-симптомы объединяются;
- отсутствие evidence не превращается в finding;
- HIGH/MEDIUM упорядочены по user impact и reach;
- результат валидируется JSON Schema/Pydantic contract.

## 6. Этап IA-03 — self-audit stage flow

### Scope

```text
login
→ workspace
→ new analysis
→ mission detail
→ evidence
→ report gate
```

### Проверяемые состояния

- успешный login;
- ошибочный login;
- running mission;
- degraded;
- blocked;
- failed;
- completed;
- report allowed/denied.

### Ключевые проверки

- keyboard-only completion;
- visible focus;
- accessible names;
- progress narration/live region;
- состояние не кодируется только цветом;
- следующий шаг понятен;
- 320 px и 200% zoom;
- длинные URL/digests доступны полностью;
- нет secrets в UI/evidence.

### Acceptance

- stage audit создаёт полный artifact manifest;
- найденные проблемы имеют воспроизводимые шаги;
- verification gaps показаны отдельно;
- verdict сохраняется в mission persistence;
- результат доступен admin без раскрытия secrets.

## 7. Этап IA-04 — automated accessibility checks

### Работы

- интегрировать axe-core либо эквивалент;
- keyboard traversal helper;
- focus order capture;
- accessible-name inspection;
- contrast measurement;
- 200% zoom / 320 px reflow checks;
- reduced-motion mode.

### Правило консолидации

Automated checker создаёт observations. Findings формирует только orchestrator после контекстной проверки и объединения корневых причин.

### Acceptance

- raw checker output хранится как evidence;
- false positives могут быть rejected с причиной;
- WCAG rule/level сохраняются в finding;
- CI не блокируется по raw observation без confirmed finding.

## 8. Этап IA-05 — fixture pack по `jakub.kr/skills`

### Fixture classes

1. buttons/surfaces;
2. typography hierarchy;
3. OKLCH/HSL palette behavior;
4. registration form accessibility;
5. grouping/layout;
6. destructive dialog writing;
7. empty state writing.

### Работы

- создать локальные минимальные before-fixtures;
- описать expected domain и finding class;
- допускаемые альтернативные fixes;
- negative fixtures, где изменение не требуется;
- regression tests для rule pack update.

### Acceptance

- skill обнаруживает класс проблемы, а не копирует after-дизайн;
- нет требования pixel-perfect;
- тесты фиксируют false positive/false negative;
- обновление rule pack не проходит без fixture regression.

## 9. Этап IA-06 — UI и API

### API

Первый вариант может использовать общий Mission Orchestrator. Целевой контракт:

```text
POST /api/interface-audits
GET  /api/interface-audits/{id}
GET  /api/interface-audits/{id}/evidence
GET  /api/interface-audits/{id}/findings
GET  /api/interface-audits/{id}/report
POST /api/interface-audits/{id}/retry
```

### UI

- audit launch form;
- scope/mode selector;
- live stage narration;
- coverage matrix;
- findings table;
- screenshot + locator viewer;
- before/after/why;
- verification gaps;
- verdict;
- rerun after remediation.

### Acceptance

- UI восстанавливается после reload;
- пользователь видит, что агент делает сейчас;
- `degraded`, `blocked`, `failed`, `inconclusive` различимы текстом и иконкой;
- findings фильтруются по severity/domain/authority;
- evidence доступно только владельцу/admin по policy.

## 10. Этап IA-07 — CI/PR gate

### Работы

- continuous mode;
- стабильные flows и test accounts;
- artifacts в GitHub Actions;
- PR summary/annotations;
- waiver с owner, reason, expiry;
- comparison с предыдущим accepted baseline.

### Начальная gate policy

Block только если:

- finding подтверждён;
- severity = HIGH;
- authority = `standard` или `aimeton_policy`;
- scope входит в обязательный flow;
- finding не имеет действующего waiver.

### Acceptance

- flaky runtime не маскируется как UI defect;
- infrastructure failure даёт `inconclusive`;
- PR содержит ссылку на artifacts;
- waiver истекает автоматически;
- baseline нельзя обновить без audit trail.

## 11. Этап IA-08 — клиентский MVP

### Пакет

`Экспресс-аудит интерфейса, доступности и потерь конверсии`.

### Результат клиента

- scope и coverage;
- 5 главных проблем;
- screenshot/locator;
- влияние на пользователя;
- бизнес-риск;
- конкретное исправление;
- quick wins и системные изменения;
- evidence confidence;
- повторная проверка.

### Ограничения MVP

- публичные страницы или предоставленный test account;
- один primary flow;
- ограниченное число экранов;
- без автоматического изменения production;
- без юридической сертификации.

### Acceptance

- результат понятен владельцу малого бизнеса;
- technical appendix доступен разработчику;
- отчёт не обещает проверку непосещённых состояний;
- повторный audit показывает resolved/open/regressed.

## 12. Очерёдность

```text
IA-00 → IA-01 → IA-02 → IA-03
                     ↓
          IA-04 → IA-05 → IA-07
                     ↓
                  IA-06 → IA-08
```

Критический путь до первой практической пользы:

```text
provenance
→ evidence collector
→ quick orchestrator
→ self-audit stage
```

## 13. Риски и парирование

| Риск | Парирование |
|---|---|
| skills остаются «умными промптами» без глаз | evidence collector является P0 capability |
| отчёт раздут одинаковыми ошибками | обязательная root-cause consolidation |
| вкусовые советы блокируют релиз | authority classes и gate policy |
| browser audit нестабилен | typed infrastructure failure и `inconclusive` |
| artifacts содержат secrets | masking, isolation, retention policy, tests |
| fork расходится с upstream | explicit sync review и snapshot changelog |
| агент утверждает больше, чем проверил | coverage matrix и `not_verified` |
| дорогой full audit тормозит MVP | начать с `quick` и одного primary flow |

## 14. Definition of Done для v0.1

- локальный versioned rule pack;
- screenshot/DOM/console/network evidence;
- quick audit с четырьмя первыми доменами;
- structured finding contract;
- consolidation/rejected/not_verified;
- self-audit stage flow;
- persisted verdict;
- тесты безопасности и cleanup;
- документация capability/passport;
- один воспроизводимый demo report.

## 15. Отложено после v0.1

- visual diff с интеллектуальной сегментацией;
- полноценный performance domain;
- conversion scoring по отраслевым моделям;
- многошаговые authenticated client flows;
- автоматическое создание patch/PR;
- continuous production monitoring;
- мультиязычный UX-writing reviewer.
