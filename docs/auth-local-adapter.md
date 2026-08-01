# SA-MVP-01B — Local Auth Adapter

## Назначение

Локальный auth-контур предназначен для ограниченного stage-тестирования AIMETON Site Auditor до подключения платформенного Supabase Auth.

Он не является вторым каноническим IAM-контуром AIMETON. Его задача — доказать пользовательский lifecycle и сохранить заменяемую границу адаптера.

## Доменные границы

Бизнес-логика зависит от интерфейсов:

- `UserRepository` — получение и изменение состояния пользователя;
- `AuthProvider` — аутентификация и lifecycle server-side session;
- `UserRole` — типизированная прикладная роль `admin/user`.

FastAPI routes зависят от `AuthProvider`, а не от SQL-запросов или конкретного внешнего провайдера.

## Локальная реализация

- SQLite хранит users и server-side sessions;
- пароль хранится только как versioned `scrypt` hash;
- клиент получает непрозрачный session token;
- в БД сохраняется только SHA-256 digest session token;
- блокировка пользователя отзывает его незавершённые сессии;
- bootstrap первого администратора разрешён только через server environment:
  - `AIMETON_BOOTSTRAP_ADMIN_USERNAME`;
  - `AIMETON_BOOTSTRAP_ADMIN_PASSWORD`;
- секреты не должны попадать в GitHub, Issues, PR, logs или API responses.

## Runtime configuration

- `AIMETON_AUTH_DB` — путь к SQLite-файлу, по умолчанию `data/auth.sqlite3`;
- `AIMETON_COOKIE_SECURE` — production/stage значение должно оставаться `true`; `false` допустимо только в локальных HTTP-тестах;
- bootstrap variables следует удалить из runtime environment после успешного создания администратора либо заменить одноразовым секретным механизмом deployment.

## Граница будущего Supabase adapter

При переходе к Supabase должны сохраниться доменные результаты:

- идентификатор пользователя;
- нормализованное имя/subject;
- активность;
- прикладная роль;
- серверное решение `current_user` / `require_admin`;
- отсутствие service-role secret в браузере.

Заменяются:

- `SQLiteUserRepository` → Supabase/PostgreSQL repository;
- `LocalAuthProvider` → JWT/Supabase Auth adapter;
- локальная session table → Supabase session/JWT lifecycle.

Не должны переноситься в бизнес-логику:

- SQL-конкретика SQLite;
- формат локального password hash;
- cookie token как доменный идентификатор;
- Supabase client/service-role детали.

## Ограничения текущего среза

В SA-MVP-01B не входят самостоятельная регистрация, email recovery, организации, сложный RBAC, billing и ownership миссий. Они развиваются отдельными вертикальными срезами после принятия локального lifecycle.

Part of #153 and #145.
