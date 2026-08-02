# AIMETON Site Auditor × WebBrain

## План развития Browser Edge и живой интеграции

Дата принятия: 2026-08-02.

Статус: **accepted for staged evaluation**.

## 1. Решение

WebBrain рассматривается не как новое ядро AIMETON Site Auditor и не как замена Search & Evidence Fabric, а как референсная реализация локального **AIMETON Browser Edge Node** — органа восприятия и действия в живом браузере пользователя.

Site Auditor сохраняет ответственность за:

- Mission Contract;
- серверный поиск, crawling и OSINT;
- квалификацию компании;
- Claim & Evidence Ledger;
- Company Profile;
- budget и provider policy;
- authoritative mission state;
- Human Review и клиентский выпуск.

Browser Edge отвечает за:

- наблюдение живой страницы;
- работу в авторизованной сессии пользователя;
- проверку сложных SPA и пользовательских маршрутов;
- локально разрешённые действия;
- visual/semantic evidence;
- события длительной миссии;
- безопасное воспроизведение проверенных workflows.

## 2. Почему это нужно Site Auditor

Текущий серверный контур умеет исследовать сайт, документы и внешние источники, но часть коммерчески значимых фактов можно установить только в живом браузере:

- действительно ли работает онлайн-запись;
- проходит ли форма заявки до подтверждения;
- есть ли скрытый чат или callback widget;
- как ведёт себя сайт после выбора города;
- доступен ли каталог после JavaScript-инициализации;
- есть ли личный кабинет и какие задачи в нём повторяются;
- какие ошибки, тупики и трения встречает клиент;
- можно ли получить нужный отчёт или выполнить операцию в кабинете без API.

Browser Edge не заменяет серверный сбор. Он подключается к дорогим, неоднозначным, авторизованным или визуально зависимым проверкам.

## 3. Целевая схема

```text
Site Auditor UI / REST / MCP
          │
          ▼
Mission Contract + Browser Task Envelope
          │
          ▼
Mission Orchestrator / Runtime
          │
          ├──────── Server SEF ──────── public web, documents, claims
          │
          └──────── Browser Edge ────── live tab, auth session, UI evidence
                                      │
                                      ▼
                              Human approval / Stop
```

Результаты обоих контуров объединяются по `mission_id`, но Browser Edge не изменяет Ledger напрямую. Он возвращает candidate evidence, которое проходит обычные evidence gates.

## 4. Принятые ограничения пилота

1. Первый runtime — Chromium.
2. Используется отдельный тестовый browser profile.
3. Upstream WebBrain применяется без глубокого форка.
4. WebBrain Cloud не используется для чувствительных сценариев.
5. LLM подключается через контролируемый AIMETON/OpenAI-compatible endpoint.
6. Strict secret handling включён.
7. Production credentials на первом этапе запрещены.
8. Основной режим пилота — Observe; Act вводится только после оценки.
9. Dev mode разрешён только в диагностических сценариях.
10. Сервер не передаёт произвольный JavaScript или низкоуровневые команды.
11. Consequential actions всегда требуют локальной политики и подтверждения.
12. Сырые traces не считаются workflow и не публикуются без очистки.

## 5. Приоритетные сценарии

### BA-01 · Проверка онлайн-записи

Цель: установить, существует ли реальный путь записи, какие данные нужны и где возникают препятствия.

Разрешения пилота:

- открыть страницы;
- нажимать только навигационные элементы;
- читать поля и сообщения;
- не отправлять форму.

Evidence:

- URL;
- semantic target;
- последовательность экранов;
- обязательные поля;
- screenshot;
- blocker/reason code.

### BA-02 · Проверка формы обращения

Цель: подтвердить существование и работоспособность формы до последнего изменяющего шага.

Пилот останавливается перед отправкой. Позже controlled Act может использовать тестовый адрес и явное подтверждение.

### BA-03 · Проверка региональности и наличия

Цель: выяснить, меняется ли предложение после выбора региона, города или склада.

### BA-04 · Проверка клиентского сервиса

Цель: найти чат, callback, мессенджеры, FAQ, скорость и форму первого контакта без отправки сообщения.

### BA-05 · Проверка личного кабинета на тестовых данных

Цель: выявить повторяемые ручные операции, пригодные для будущего AI-оператора.

Только отдельный тестовый аккаунт.

### BA-06 · Визуальная верификация результатов серверного анализа

Цель: проверить конкретные гипотезы SEF, например наличие цен, услуги, вакансии, записей, CTA или устаревших страниц.

### BA-07 · Учебный workflow

Цель: одну успешную тестовую миссию преобразовать в параметризованный workflow, повторно выполнить и оценить устойчивость.

## 6. Browser Task Envelope v0.1

Пример задания от Site Auditor:

```json
{
  "schema_version": "0.1.0",
  "mission_id": "mission_...",
  "task_id": "browser_task_...",
  "company": {
    "name": "Example Clinic",
    "canonical_url": "https://example.ru"
  },
  "intent": "Проверить наличие и доступность онлайн-записи",
  "mode": "observe",
  "allowed_origins": ["https://example.ru"],
  "allowed_capabilities": [
    "read_page",
    "navigate_same_origin",
    "click_navigation",
    "screenshot"
  ],
  "forbidden_capabilities": [
    "submit",
    "type_secret",
    "execute_js",
    "download",
    "cross_origin_navigation"
  ],
  "limits": {
    "max_steps": 30,
    "max_model_calls": 20,
    "deadline_seconds": 180
  },
  "success_criteria": [
    "Наличие онлайн-записи подтверждено или опровергнуто",
    "Сформирован evidence package"
  ],
  "evidence_policy": "semantic_and_visual"
}
```

## 7. Evidence package v0.1

```json
{
  "schema_version": "0.1.0",
  "mission_id": "mission_...",
  "task_id": "browser_task_...",
  "run_id": "edge_run_...",
  "node_id": "browser_edge_lab_01",
  "status": "completed",
  "started_at": "...",
  "finished_at": "...",
  "observations": [
    {
      "url": "https://example.ru/booking",
      "origin": "https://example.ru",
      "claim": "На сайте доступна форма онлайн-записи",
      "semantic_target": {
        "role": "button",
        "name": "Записаться онлайн"
      },
      "postcondition": "Открыта форма выбора услуги и даты",
      "screenshot_ref": "evidence://...",
      "confidence": 0.9
    }
  ],
  "reason_codes": [],
  "trace_ref": "trace://..."
}
```

Browser evidence имеет статус `candidate`, пока не пройдёт Evidence Guard и не будет связано с claim/locator в Ledger.

## 8. Живой репортаж миссии

Пользователь должен видеть, что агент работает, где находится и почему остановился. Для Browser Edge вводится поток событий, отображаемый в текущем живом интерфейсе Site Auditor.

Базовые стадии:

```text
📥 Поручение принято
🧭 Строю безопасный план
🌐 Открываю страницу
👁 Читаю интерфейс
🔎 Ищу целевой элемент
🖱 Выполняю разрешённый шаг
🧪 Проверяю результат
📸 Сохраняю доказательство
🛡 Ожидаю подтверждение
⚠️ Работаю в ограниченном режиме
⛔ Обнаружен блокер
✅ Проверка завершена
```

Каждое событие должно содержать:

- `mission_id`;
- `task_id`;
- `run_id`;
- `stage`;
- краткое человекочитаемое сообщение;
- `requires_user_action`;
- `reason_code`;
- ссылку на evidence, если оно уже появилось;
- heartbeat/last_seen для обнаружения зависания.

Текущий UI длинной миссии должен использовать этот же общий event contract, а не отдельный специальный индикатор только для WebBrain.

## 9. Reason codes пилота

Минимальный набор:

- `EDGE_AUTH_REQUIRED`;
- `EDGE_PERMISSION_DENIED`;
- `EDGE_ORIGIN_NOT_ALLOWED`;
- `EDGE_TARGET_NOT_FOUND`;
- `EDGE_TARGET_AMBIGUOUS`;
- `EDGE_CAPTCHA_BLOCKED`;
- `EDGE_PAGE_CHANGED`;
- `EDGE_UNSUPPORTED_SURFACE`;
- `EDGE_PLAN_REJECTED`;
- `EDGE_POSTCONDITION_FAILED`;
- `EDGE_OUTCOME_UNKNOWN`;
- `EDGE_STEP_LIMIT`;
- `EDGE_MODEL_LIMIT`;
- `EDGE_DEADLINE_EXCEEDED`;
- `EDGE_USER_STOPPED`;
- `EDGE_NODE_DISCONNECTED`;
- `EDGE_EVIDENCE_INCOMPLETE`;
- `EDGE_PROMPT_INJECTION_BLOCKED`.

## 10. План реализации

### Фаза 0 · Документация и граница

- зафиксировать Browser Edge в архитектурном репозитории;
- принять этот план;
- запретить смешение Browser Edge с authoritative mission state;
- определить общую таксономию событий.

Критерий выхода: архитектурные документы согласованы.

### Фаза 1 · Ручной upstream lab

- установить WebBrain из upstream в отдельный Chromium profile;
- настроить AIMETON provider;
- отключить WebBrain Cloud и лишние permissions;
- включить strict secret handling;
- провести BA-01…BA-04 вручную на 5–10 сайтах;
- экспортировать traces;
- составить failure taxonomy.

Критерий выхода:

- не менее 70% Observe-сценариев дают проверяемое evidence;
- нет несанкционированных действий;
- понятны стоимость, latency и типовые блокеры.

### Фаза 2 · AIMETON skill pack и site adapters

- создать AIMETON skill с правилами evidence и остановки;
- добавить 3–5 адаптеров для целевых российских сайтов;
- локализовать подсказки;
- проверить, что adapter не содержит хрупкую энциклопедию selectors;
- связать trace labels с mission event taxonomy.

Критерий выхода: успешность и число шагов улучшаются относительно чистого upstream.

### Фаза 3 · Thin Bridge prototype

Предлагаемый локальный контур:

```text
Site Auditor backend
  ⇅ authenticated WebSocket / localhost HTTP
AIMETON Browser Bridge
  ⇅ extension runtime messaging
WebBrain-derived runtime
```

Минимальные операции:

- `mission.start`;
- `mission.cancel`;
- `mission.status`;
- `approval.resolve`;
- `evidence.emit`;
- `trace.export`.

Требования:

- signed/authenticated task envelope;
- TTL и replay protection;
- origin/capability allowlist;
- heartbeat;
- emergency stop;
- отсутствие внешнего unauthenticated listener;
- локальный permission gate нельзя обходить.

Критерий выхода: одна Observe-миссия запускается из Site Auditor и возвращает события и evidence по тому же `mission_id`.

### Фаза 4 · UI mission ticker

- показать Browser Edge stages в истории миссии;
- отображать last heartbeat;
- различать `running`, `awaiting_approval`, `blocked`, `degraded`, `completed`, `failed`;
- добавить Stop;
- показать последний безопасный шаг и причину блокировки;
- не раскрывать secrets и raw model prompts.

Критерий выхода: оператор понимает состояние миссии без доступа к server logs.

### Фаза 5 · Controlled Act

- тестовые формы и аккаунты;
- explicit approval перед submit/upload/download;
- postcondition verification;
- duplicate-submit guard;
- unknown-outcome stop;
- security review и retention policy.

Критерий выхода: минимум три controlled Act-сценария проходят без нарушения policy.

### Фаза 6 · Workflow learning

- выбрать успешную трассу;
- очистить runtime values, secrets, ref_id, coordinates и brittle selectors;
- определить parameters, URL scope и semantic targets;
- добавить pre/postconditions;
- повторно выполнить;
- зарегистрировать как experimental capability.

Критерий выхода: workflow повторяется на свежей сессии и безопасно останавливается при изменении страницы.

### Фаза 7 · Решение о форке

Форк WebBrain оправдан, если подтверждены коммерческие сценарии и нужны как минимум две возможности:

- внешний mission API;
- стабильный event/evidence protocol;
- корпоративная дистрибуция и политики;
- централизованный capability registry;
- подписанные workflow-пакеты;
- глубокая интеграция с Site Auditor;
- заморозка стабильной версии при слишком быстром upstream cadence.

Если условия не выполнены, продолжается тонкая интеграция с upstream.

## 11. Что не делать сейчас

- не заменять WebBrain серверный crawler;
- не переносить authoritative Ledger в расширение;
- не давать агенту доступ к production banking/почте/админке;
- не открывать Bridge во внешний интернет;
- не запускать массовую охоту из пользовательского браузера;
- не хранить API keys в экспортируемом config без отдельной процедуры;
- не считать screenshot достаточным evidence без URL, времени и semantic context;
- не делать глубокий форк до измеримого пилота;
- не создавать отдельную несовместимую систему статусов миссии.

## 12. Метрики

Обязательные:

- observe completion rate;
- verified completion rate;
- evidence completeness;
- human intervention rate;
- permission denial rate;
- prompt-injection block count;
- unknown outcome count;
- model calls;
- agent steps;
- median/p95 latency;
- cost per mission;
- loop/retry count;
- site-adapter benefit;
- workflow replay success;
- доля миссий, где Browser Edge добавил факт, недоступный серверному контуру.

## 13. Критерии общего успеха

Интеграция считается перспективной, если:

1. Browser Edge дополняет, а не дублирует SEF.
2. Пользователь видит живое состояние длинной миссии.
3. Все действия ограничены intent, capability и origin.
4. Evidence объединяется с серверной миссией по `mission_id`.
5. Неизвестный исход приводит к остановке, а не слепому retry.
6. Есть хотя бы один сценарий, за который клиент готов платить.
7. Есть хотя бы один безопасно повторяемый workflow.
8. Стоимость сопровождения upstream/bridge ниже стоимости разработки собственного browser agent с нуля.

## 14. Ближайший рабочий пакет

Первый практический пакет после принятия документа:

- подготовить Chromium profile `AIMETON Edge Lab`;
- зафиксировать upstream commit/version WebBrain;
- настроить контролируемый LLM endpoint;
- выбрать 5 тестовых сайтов из текущего live-теста интерфейса;
- определить BA-01/BA-02 task envelopes;
- запустить Observe-only проверки;
- выгрузить и разобрать traces;
- сформировать таблицу результатов и go/no-go для Thin Bridge.

## 15. Связанные документы

- архитектурный ADR и спецификация Browser Edge в `Dimar4713/aimeton-architecture`;
- `docs/plans/AIMETON_SEF_tactical_plan_2026-07-28.md`;
- `docs/architecture/SEF_HUMAN_REVIEW_REPORT_V1.md`;
- Mission Contract, Provider Gateway, document fetch и Evidence Ledger контракты этого репозитория.
