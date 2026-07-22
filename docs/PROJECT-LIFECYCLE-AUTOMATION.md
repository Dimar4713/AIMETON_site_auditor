# GitHub Project lifecycle automation

## Назначение

Workflow `.github/workflows/project-status-sync.yml` синхронизирует Issues и Pull Requests с полем `Status` GitHub Project V2.

Поддерживаемые состояния:

- `Backlog`;
- `In Progress`;
- `In Review`;
- `Validation`;
- `Blocked`;
- `Done`.

## Настройка репозитория

В `Settings → Secrets and variables → Actions` должны быть заданы:

### Secret

- `PROJECTS_TOKEN` — fine-grained PAT владельца проекта с доступом к репозиторию и GitHub Projects V2. Токену нужны права на чтение/изменение проекта и Issues/PR. Не использовать основной пароль или токен с лишними правами.

### Variables

- `PROJECT_OWNER` — логин пользователя или организации, владеющей Project V2, например `Dimar4713`;
- `PROJECT_NUMBER` — номер Project V2 из URL проекта.

Поле проекта должно называться строго `Status` и содержать варианты с точными именами:

`Backlog`, `In Progress`, `In Review`, `Validation`, `Blocked`, `Done`.

## Правила переходов

| Событие или признак | Status |
|---|---|
| новый обычный Issue | `Backlog` |
| reopened Issue | `In Progress` |
| draft PR | `In Progress` |
| PR открыт/переведён в ready/review requested | `In Review` |
| заголовок начинается с `VALIDATION` | `Validation` |
| label `status:validation` | `Validation` |
| label `status:in-review` | `In Review` |
| label `status:in-progress` | `In Progress` |
| label `status:backlog` | `Backlog` |
| label `blocked` или `status:blocked` | `Blocked` |
| Issue/PR закрыт | `Done` |

Приоритет правил:

1. ручной `workflow_dispatch`;
2. закрытие → `Done`;
3. блокировка → `Blocked`;
4. явный `status:*` label;
5. префикс `VALIDATION`;
6. стандартная логика Issue/PR.

## Возврат из Blocked

Перед переводом в `Blocked` workflow читает текущий статус и добавляет служебный label:

- `resume:backlog`;
- `resume:in-progress`;
- `resume:in-review`;
- `resume:validation`.

После удаления label `blocked`/`status:blocked` карточка возвращается в сохранённое состояние. Если resume-label отсутствует, безопасный fallback — `In Progress`.

Служебный resume-label удаляется после успешного возврата.

## Ручная коррекция

`Actions → Project Status Sync → Run workflow`:

- выбрать `issue` или `pull_request`;
- указать номер;
- выбрать требуемый Status.

Ручной запуск используется для миграции старых карточек и исправления статуса после изменения процессной модели.

## Миграция Issue #35

После настройки `PROJECTS_TOKEN`, `PROJECT_OWNER` и `PROJECT_NUMBER` запустить workflow вручную:

- item kind: `issue`;
- item number: `35`;
- target status: `Validation`.

После этого новые Issues с префиксом `VALIDATION` будут автоматически попадать в `Validation`.

## Ограничения

- GitHub Actions `GITHUB_TOKEN` обычно недостаточен для пользовательского Project V2, поэтому применяется отдельный минимально привилегированный `PROJECTS_TOKEN`;
- workflow не создаёт отсутствующие варианты поля `Status`;
- переименование поля или вариантов требует синхронного обновления документации и автоматики;
- `Blocked` является боковым состоянием, а не последовательным этапом жизненного цикла.
