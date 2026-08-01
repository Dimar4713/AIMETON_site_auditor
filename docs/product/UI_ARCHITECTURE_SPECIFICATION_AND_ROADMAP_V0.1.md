# AIMETON Site Auditor — архитектурный проект, спецификация UI и дорожная карта

**Статус:** проектный baseline v0.1  
**Связанные задачи:** #145, #144, #80  
**Основание:** внешний аудит UI от 2026-07-29 и принятые решения по capability-driven интерфейсу.

## 1. Цель

Довести AIMETON Site Auditor до логически завершённого рабочего продукта для ограниченного тестирования с упрощённым пользовательским и административным контуром, не создавая тупиковую временную архитектуру.

Продукт должен обеспечивать полный цикл:

1. вход пользователя;
2. запуск аудита;
3. наблюдение за выполнением;
4. просмотр evidence и УДП;
5. получение разрешённого отчёта;
6. восстановление состояния после перезагрузки и рестарта;
7. административное наблюдение и безопасное управление.

После принятия MVP локальные реализации Auth и persistence заменяются адаптерами Supabase без изменения доменной логики.

## 2. Главный архитектурный тезис

Backend уже реализует больше функций, чем текущий Web UI. UI нельзя строить как набор кнопок к каждому endpoint. Он строится вокруг пользовательских задач, доказательного состояния результата и effective capabilities.

Интерфейс является композицией доступных возможностей, но не границей безопасности.

```text
Authentication
    + Authorization
    + Entitlement
    + Quota
    + Runtime/Evidence gates
              ↓
      Effective capabilities
              ↓
 Navigation / actions / limits
```

Каждый backend endpoint повторно проверяет права, владение, тарифные возможности, лимиты и состояние миссии.

## 3. Границы MVP

### Входит

- локальный вход по заранее созданным учётным записям;
- роли `admin` и `user`;
- тестовый план `test`;
- серверная история миссий;
- владение миссиями пользователем;
- пользовательский workspace;
- административный workspace;
- состояние `running/degraded/blocked/completed`;
- evidence, УДП и Report Gate;
- health/search diagnostics;
- capability-driven navigation;
- восстановление после restart/redeploy.

### Не входит

- самостоятельная регистрация;
- email recovery;
- организации и сложный RBAC;
- коммерческий биллинг;
- публичный SaaS;
- полный Supabase-контур;
- полный reviewer workflow;
- DOCX/XLSX-конструктор отчётов.

## 4. Пользовательские роли

### User

Может:

- входить и выходить;
- видеть свои миссии;
- запускать доступные услуги;
- смотреть состояние, evidence, УДП и разрешённый отчёт;
- продолжать работу после перезагрузки страницы.

Не может:

- видеть чужие миссии;
- управлять пользователями;
- видеть secrets и внутренние токены;
- выполнять административный retry;
- обходить Report Gate.

### Admin

Дополнительно может:

- создавать и блокировать локальных пользователей;
- сбрасывать пароль;
- видеть все миссии;
- видеть provider/crawler/AI diagnostics;
- видеть причины degradation/block;
- выполнять безопасный retry;
- управлять тестовыми лимитами;
- просматривать admin audit trail.

## 5. Capability-driven UI

Роль, тариф и лимит не смешиваются.

Начальный контракт:

```text
plan = test
roles = admin | user
```

### User capabilities

- `analyze_site`
- `view_own_missions`
- `view_own_evidence`
- `view_own_sufficiency`
- `view_allowed_report`
- `use_analysis_chat`

### Admin capabilities

- все user capabilities;
- `manage_users`
- `view_all_missions`
- `view_diagnostics`
- `retry_mission`
- `manage_test_limits`
- `view_admin_audit`

### Будущие услуги

- `company_intelligence`
- `company_hunt`
- `company_compare`
- `sef_profile`
- `sef_report`
- `evidence_review`
- `api_access`
- `mcp_access`
- `extended_sources`
- `priority_execution`

Frontend получает effective capabilities через серверный контракт `/api/me/capabilities` и строит навигацию динамически.

Недоступная функция может быть:

- скрыта — административная или опасная;
- показана заблокированной — услуга другого тарифа;
- показана с остатком лимита;
- временно отключена из-за degradation или maintenance.

## 6. Информационная архитектура

### Общие маршруты

```text
#/login
#/workspace
#/missions
#/missions/{mission_id}
#/missions/{mission_id}/evidence
#/missions/{mission_id}/report
#/help/methodology
```

### Admin routes

```text
#/admin
#/admin/users
#/admin/missions
#/admin/diagnostics
#/admin/audit
```

### Будущие маршруты

```text
#/intelligence
#/hunt
#/compare
#/catalog/sources
#/catalog/osint
#/catalog/handbook
```

## 7. Спецификация экранов

### 7.1 Login

Содержит:

- логин;
- пароль;
- явное сообщение об ошибке;
- состояние блокировки учётной записи;
- информацию о версии stage.

Требования:

- пароль не хранится во frontend;
- сессия передаётся secure/httpOnly cookie;
- после logout сессия недействительна;
- redirect возвращает только на разрешённый route.

### 7.2 User workspace

Содержит:

- приветствие и роль;
- доступные услуги;
- остатки лимитов;
- кнопку запуска анализа;
- последние миссии;
- status bar системы;
- заблокированные услуги более высокого пакета без раскрытия внутренней реализации.

### 7.3 New analysis

Поля:

- URL;
- необязательное название компании;
- цель анализа;
- подтверждение запуска.

После запуска создаётся mission и выполняется переход на `#/missions/{id}`.

### 7.4 Mission list

Колонки/поля:

- компания/URL;
- дата запуска;
- состояние;
- достигнутый УДП;
- critical gaps;
- доступность отчёта;
- последнее действие.

Фильтры:

- состояние;
- дата;
- URL/компания.

User видит только свои миссии. Admin может переключить режим «все миссии».

### 7.5 Mission detail

Содержит:

- идентификатор миссии;
- actor/owner;
- состояние;
- этап выполнения;
- before/after УДП;
- critical gaps;
- next action и причина;
- evidence summary;
- typed degradation/block reason;
- кнопки, разрешённые capability policy.

### 7.6 Evidence view

Каждый источник показывает:

- URL и название;
- evidence level;
- lifecycle state;
- classification state;
- verification note;
- locator;
- digest;
- связь с утверждением/разделом профиля.

Уровни доказательности визуально различаются, но цвет не является единственным носителем смысла.

### 7.7 Report view

Показывает:

- статус Report Gate;
- достигнутый УДП;
- незакрытые blockers;
- выпущенные claims;
- integrity digests;
- sign-off metadata.

Отчёт не выпускается ниже требуемого УДП и при критических gaps независимо от роли или тарифа.

### 7.8 Admin users

Функции:

- создать пользователя;
- назначить роль `user/admin`;
- заблокировать/разблокировать;
- сбросить пароль;
- установить тестовые лимиты;
- увидеть последнее успешное действие без раскрытия пароля или session token.

### 7.9 Admin diagnostics

Показывает:

- app version и deployment SHA;
- health подсистем;
- search providers;
- configured/paid/circuit state/quota;
- crawler/AI status;
- последние typed failures;
- безопасный retry при наличии capability.

## 8. Состояния UI

Каждый долгий процесс обязан иметь типизированное состояние:

```text
queued
planned
running
validation
completed
degraded
blocked
failed
cancelled
```

UI не маскирует `degraded` или `blocked` как успех.

Прогресс отображается этапами:

1. подготовка миссии;
2. загрузка страницы;
3. извлечение контента;
4. внешний поиск;
5. анализ;
6. оценка достаточности;
7. формирование отчёта.

Первый MVP может использовать polling. SSE вводится отдельным вертикальным срезом после стабилизации mission persistence.

## 9. Техническая архитектура frontend

### Принципы

- единая функция/слой рендера без MutationObserver-патчей;
- маршрутизация минимум через hash router;
- API client отделён от представления;
- session/capabilities хранятся в едином application state;
- URL конкретной миссии пригоден для deep link;
- secrets отсутствуют в browser bundle;
- frontend не принимает окончательное решение о доступе.

### Рекомендуемые модули

```text
static/js/
  api-client.js
  auth-store.js
  capability-store.js
  router.js
  mission-store.js
  components/
  pages/
    login.js
    workspace.js
    mission-list.js
    mission-detail.js
    evidence.js
    report.js
    admin-users.js
    admin-diagnostics.js
```

На первом этапе допустимо сохранить текущий технологический стек без перехода на React/Next.js. Решение о framework migration принимается только после рабочего MVP.

## 10. Backend-контракты MVP

Необходимые новые или нормализованные endpoints:

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/me
GET  /api/me/capabilities

GET  /api/missions
POST /api/missions
GET  /api/missions/{id}
GET  /api/missions/{id}/evidence
GET  /api/missions/{id}/report
POST /api/missions/{id}/retry

GET  /api/admin/users
POST /api/admin/users
PATCH /api/admin/users/{id}
POST /api/admin/users/{id}/reset-password
GET  /api/admin/missions
GET  /api/admin/diagnostics
GET  /api/admin/audit
```

Существующие `/api/analyze`, SEF и runtime endpoints могут использоваться через application service/adapters, но не должны образовывать параллельные канонические хранилища.

## 11. Persistence MVP

До Supabase допустима локальная PostgreSQL или SQLite только за интерфейсами:

- `AuthProvider`;
- `UserRepository`;
- `SessionRepository`;
- `MissionRepository`;
- `UsageRepository`;
- `AdminAuditRepository`.

Канонически сохраняются:

- users и password hashes;
- sessions;
- mission ownership;
- mission snapshot;
- turns;
- sufficiency turn records;
- artifact/evidence references;
- report metadata;
- usage reservations/consumption;
- admin audit events.

Stable identifiers и digests должны сохраниться при будущей миграции в Supabase.

## 12. Безопасность

- современные password hashes;
- secure/httpOnly/sameSite cookie;
- CSRF-защита для state-changing операций;
- server-side authorization;
- object-level access check для каждой mission;
- rate limit login;
- session expiration и revoke;
- audit административных действий;
- отсутствие service secrets во frontend;
- негативные cross-user tests.

## 13. Наблюдаемость

Пользователь видит безопасную часть:

- состояние системы;
- состояние своей миссии;
- объяснимую причину деградации;
- доступность отчёта.

Admin видит дополнительно:

- provider/circuit status;
- deployment SHA;
- typed failure codes;
- retry eligibility;
- audit events.

Логи и UI не показывают пароли, токены, API keys и необработанные secrets.

## 14. Дорожная карта реализации

### Этап A — Product gap audit

- сверить текущий UI с API и новым Mission Orchestrator;
- определить пригодные endpoints;
- исключить дубли;
- зафиксировать screen/API matrix.

**Результат:** подтверждённый backlog без предположений о готовности endpoint.

### Этап B — Auth, role и capabilities

- локальные users;
- password hashing;
- session lifecycle;
- `admin/user`;
- `CapabilityPolicy`;
- `/api/me` и `/api/me/capabilities`;
- negative authorization tests.

**Результат:** защищённый вход и динамическое меню.

### Этап C — Mission persistence и ownership

- repository adapter;
- owner_id;
- snapshot/turn/УДП persistence;
- restart recovery;
- cross-user isolation;
- migration digest.

**Результат:** серверная история и восстановление миссий.

### Этап D — User workspace

- dashboard;
- запуск анализа;
- mission list/detail;
- progress/state;
- evidence;
- Report Gate;
- deep links.

**Результат:** замкнутый пользовательский сценарий.

### Этап E — Admin workspace

- users;
- all missions;
- diagnostics;
- limits;
- safe retry;
- audit trail.

**Результат:** управляемый тестовый stage.

### Этап F — UI quality and transparency

- убрать MutationObserver;
- status bar;
- evidence badges;
- typed errors;
- chat по mission/session id;
- accessibility и responsive pass.

### Этап G — Stage acceptance

- exact deploy SHA;
- один admin и два users;
- cross-user negative tests;
- restart/redeploy evidence;
- реальные кейсы `dedal24.ru` и `slavdom24.ru`;
- отчёт не выпускается ниже L4;
- независимый verdict.

### Этап H — Следующее расширение после MVP

- company intelligence;
- hunt;
- compare;
- каталоги;
- расширенный SEF UI;
- Supabase migration по #144.

## 15. Критерии готовности MVP

- [ ] пользователь входит и выходит;
- [ ] обычный пользователь не имеет admin-доступа;
- [ ] пользователь запускает аудит;
- [ ] пользователь видит только свои миссии;
- [ ] состояние переживает перезагрузку страницы;
- [ ] users, missions и УДП переживают restart/redeploy;
- [ ] evidence и УДП доступны из mission detail;
- [ ] typed degradation не маскируется успехом;
- [ ] Report Gate исполняется сервером;
- [ ] admin управляет локальными users;
- [ ] admin видит диагностику и все миссии;
- [ ] UI строится по effective capabilities;
- [ ] локальные adapters заменяемы Supabase-реализациями;
- [ ] stage пригоден для ограниченного практического тестирования.

## 16. Связь с будущей платформенной БД

Этот документ не задаёт финальную платформенную схему AIMETON. Он фиксирует доменные контракты, которые должны быть перенесены в `aimeton_supbase`:

- identity пользователя;
- role/entitlement/quota;
- ownership;
- mission snapshot и turns;
- evidence references и digests;
- sufficiency trace;
- reports;
- audit events.

Переход на Supabase выполняется заменой repository/auth adapters и миграцией данных, а не переписыванием UI-сценариев и бизнес-логики.

## 17. Управление изменениями

Любое изменение UI должно указывать:

- пользовательский сценарий;
- affected capability;
- backend contract;
- состояния success/degraded/blocked;
- evidence безопасности;
- критерий приёмки;
- связь с #145 или отдельной issue.

Документ обновляется при изменении границ MVP, маршрутов, ролей, capability contract или порядка этапов.