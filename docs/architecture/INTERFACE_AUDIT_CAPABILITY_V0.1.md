# AIMETON Site Auditor — Interface Audit Capability v0.1

**Статус:** принято к развитию  
**Дата:** 2026-08-03  
**Каноническое основание:** `aimeton-architecture/Docs/ADR/ADR-010_Контур_аудита_интерфейсов_и_управление_внешними_skills.md`  
**Методический donor:** `jakubkrehel/skills`  
**Сохранённый fork:** `Dimar4713/skills`  
**Snapshot:** `a67333399dabbc71d7778962cb9c4fb9b86a00d0`  
**Демонстрационные образцы:** `https://jakub.kr/skills`

## 1. Цель

Добавить в Site Auditor исполнимую capability `interface_audit`, которая проводит доказательный аудит реального интерфейса сайта или web-приложения и выдаёт:

- консолидированные findings по корневым причинам;
- runtime evidence;
- приоритет и влияние на пользователя/бизнес;
- точные рекомендации;
- формальный verdict;
- machine-readable результат для CI, отчёта и повторного аудита.

Capability должна использоваться и для самопроверки stage-интерфейса AIMETON.

## 2. Что уже есть

В репозитории существует Playwright-based web rendering capability:

```text
app/capabilities/web_rendering/
├── playwright_fetcher.py
├── contract.py
├── resolver.py
└── passport.yaml
```

Текущий `fetch_rendered_site`:

- запускает headless Chromium;
- проверяет публичность URL;
- загружает страницу;
- ожидает DOM/network idle;
- получает HTML;
- извлекает title и visible text;
- возвращает `RenderedPage`.

Текущий контракт содержит только:

```text
final_url
title
text
provider
html_bytes
```

Это достаточное тело для динамического извлечения текста, но недостаточное для аудита интерфейса.

## 3. Архитектурное решение

Не создавать второй независимый browser stack. Расширить существующий `web_rendering` и построить поверх него новый контур:

```text
InterfaceAuditMission
       ↓
InterfaceEvidenceCollector
       ↓
AutomatedChecks + DomainReviewers
       ↓
FindingConsolidator
       ↓
InterfaceAuditReportGate
       ↓
JSON / UI / report / CI annotations
```

### 3.1. Компоненты

```text
app/capabilities/interface_audit/
├── contract.py
├── orchestrator.py
├── scope.py
├── evidence_collector.py
├── automated_checks.py
├── rule_pack.py
├── reviewers/
│   ├── accessibility.py
│   ├── layout.py
│   ├── writing.py
│   ├── typography.py
│   ├── colors.py
│   ├── polish.py
│   ├── runtime.py
│   ├── observability.py
│   ├── trust.py
│   └── conversion.py
├── consolidator.py
├── verdict.py
└── passport.yaml
```

Методические тексты не должны быть размазаны по prompt-коду. Rule pack версионируется отдельно и загружается как локальный immutable snapshot миссии.

## 4. Расширение browser evidence

Новый collector должен уметь получать:

- full-page и viewport screenshots;
- DOM snapshot;
- stable locators/selectors;
- viewport, device scale factor и user agent;
- theme: light/dark;
- locale и document language;
- reduced-motion state;
- accessibility tree или эквивалентный snapshot;
- console messages;
- page errors;
- failed/blocked network requests;
- navigation redirects;
- interaction trace;
- timings;
- source mapping/locator, если анализируется собственный репозиторий.

### 4.1. Предлагаемое расширение контракта

```python
@dataclass(frozen=True)
class InterfacePageEvidence:
    final_url: str
    title: str
    visible_text: str
    provider: str
    html_bytes: int
    viewport: str
    locale: str | None
    color_scheme: str
    reduced_motion: bool
    screenshot_refs: tuple[str, ...]
    dom_snapshot_ref: str
    accessibility_snapshot_ref: str | None
    console_ref: str | None
    network_ref: str | None
    trace_ref: str | None
    captured_at: str
    digest: str
```

Большие artifacts не помещаются внутрь mission JSON: контракт хранит ссылки, metadata и digests.

## 5. Scope и режимы

### `quick`

- primary path;
- desktop + narrow mobile viewport;
- основные states;
- только HIGH/MEDIUM;
- до 5 root-cause findings.

### `full`

- заявленный flow;
- desktop/mobile;
- light/dark при наличии;
- loading/empty/error/degraded/blocked;
- keyboard traversal;
- до 15 root-cause findings.

### `continuous`

- заранее определённые flows;
- regression fixtures;
- baseline artifacts;
- CI verdict и waiver policy.

## 6. Домены проверки

### Первая волна — P0/P1

1. Accessibility.
2. Layout.
3. Writing.
4. Runtime/Observability.

Именно они сильнее всего влияют на успешное завершение задачи и объяснимость долгой миссии AIMETON.

### Вторая волна — P2

5. Typography.
6. Colors.
7. Polish.
8. Trust.

### Третья волна — P3

9. Performance.
10. Conversion.

## 7. Finding contract

```json
{
  "finding_id": "uif_01J...",
  "rule_id": "AIMETON.UI.A11Y.ACCESSIBLE_NAME",
  "rule_pack_version": "0.1.0",
  "domain": "accessibility",
  "severity": "high",
  "authority": "standard",
  "location": {
    "route": "#/missions/123",
    "screen": "Mission detail",
    "component": "Retry button",
    "selector": "button.retry",
    "source": "static/js/pages/mission-detail.js:214"
  },
  "before": "<button><RetryIcon /></button>",
  "after": "Add an accessible name and hide the decorative icon",
  "why": "The icon-only control has no accessible name",
  "user_impact": "Screen-reader users cannot identify the retry action",
  "evidence_refs": [
    "artifact://interface-audit/.../screenshot.png",
    "artifact://interface-audit/.../a11y.json"
  ],
  "verification": "confirmed",
  "confidence": 0.98,
  "root_cause_group": "icon-button-contract"
}
```

### `authority`

- `standard`;
- `aimeton_policy`;
- `project_convention`;
- `heuristic`.

В CI по умолчанию блокируют только подтверждённые HIGH findings классов `standard` и `aimeton_policy`. Остальные политики задаются отдельно.

## 8. Consolidation

Один системный дефект должен формировать один finding со списком мест проявления.

Примеры:

- общий компонент icon button без accessible name;
- один неправильный status token на нескольких экранах;
- один контракт ошибок, выдающий бессодержательные сообщения;
- единый fixed-height container, обрезающий локализованный текст.

Consolidator не должен раздувать отчёт по числу DOM-узлов.

## 9. Verification и rejected candidates

Результат миссии содержит:

```text
findings[]
considered_rejected[]
not_verified[]
checks[]
verdict
```

`not_verified` не считается finding. При невозможности проверить критическую часть scope verdict становится `inconclusive`.

## 10. Образцы `jakub.kr/skills`

Сайт с before/after-примерами используется как исходный fixture catalog:

- UI surfaces/buttons;
- typography hierarchy;
- OKLCH/HSL comparison;
- registration form/accessibility;
- grouping/layout;
- destructive dialog writing;
- empty state writing.

Для каждого fixture сохраняются:

- тип проблемы;
- ожидаемый domain;
- ожидаемый authority (`heuristic` либо policy в адаптированном тесте);
- минимальный expected finding;
- допустимые альтернативные fixes.

Pixel-perfect совпадение с after-образцом не требуется.

## 11. Самопроверка AIMETON

Первыми поддерживаемыми flows должны стать:

1. Login: success, invalid credentials, blocked user.
2. Workspace: capabilities, limits, disabled services.
3. New analysis: URL validation и launch.
4. Mission detail: live progress, stage narration, recovery.
5. Degraded/blocked/failed states.
6. Evidence view.
7. Report Gate.
8. Admin diagnostics и retry.

Обязательные проверки:

- полный путь клавиатурой;
- visible focus;
- доступные имена контролов;
- объявление динамического progress через live region;
- state не передаётся только цветом;
- 320 px и 200% zoom;
- длинные URL/digests не теряются без способа раскрытия;
- причины block/degradation объясняют следующий шаг;
- secrets не попадают в UI artifacts.

## 12. API и UI

Предлагаемые endpoints после стабилизации application service:

```text
POST /api/interface-audits
GET  /api/interface-audits/{id}
GET  /api/interface-audits/{id}/evidence
GET  /api/interface-audits/{id}/findings
GET  /api/interface-audits/{id}/report
POST /api/interface-audits/{id}/retry
```

До выделения отдельного mission type capability может выполняться через общий Mission Orchestrator.

UI должен показывать:

- scope и coverage;
- текущий этап сбора evidence;
- число findings по severity/domain;
- verification gaps;
- screenshots и locator;
- before/after;
- verdict;
- повторную проверку после исправления.

## 13. Безопасность

Collector MUST:

- использовать существующую проверку public URL/SSRF guard;
- блокировать опасные схемы и приватные адреса;
- ограничивать размер HTML и artifacts;
- иметь timeout и cancellation;
- очищать cookies/local storage между независимыми миссиями;
- маскировать tokens, passwords и персональные данные в logs/artifacts;
- не выполнять destructive actions без отдельного test mandate;
- сохранять traceability actor → mission → artifacts.

## 14. Report Gate

`approve` разрешён только при подтверждённом coverage заявленного scope и отсутствии actionable findings.

`block`:

- хотя бы один подтверждённый HIGH;
- доказана невозможность завершить ключевую задачу;
- подтверждена системная недоступность;
- интерфейс вводит в заблуждение с риском потери данных.

`inconclusive`:

- авторизация/anti-bot не позволили проверить основной flow;
- runtime artifacts неполны;
- заявленный state не удалось воспроизвести;
- проверка была прервана до достаточного УДП.

## 15. Не входит в v0.1

- юридическая сертификация WCAG;
- автоматическое исправление production-кода;
- полноценные user research sessions;
- penetration testing;
- нагрузочное тестирование;
- гарантированная оценка конверсии без бизнес-данных.
