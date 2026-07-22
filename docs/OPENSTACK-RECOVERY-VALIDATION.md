# OpenStack snapshot recovery validation

## Назначение

Workflow `.github/workflows/openstack-recovery-validation.yml` проверяет возможность создать отдельную временную VM из ранее созданного snapshot. Рабочий `aimeton-main-server` не перестраивается, не останавливается и не удаляется.

## Инварианты безопасности

- допустимы только имена `aimeton-validation-*`;
- UUID рабочей VM берётся из `OPENSTACK_SERVER_ID` и запрещён для удаления;
- `plan` не выполняет write-операций;
- `create` требует точную строку `CREATE <validation_name>`;
- `delete` требует UUID временной VM и строку `DELETE <validation_server_id>`;
- имя и UUID удаляемого ресурса сверяются повторно;
- workflow не удаляет snapshots, volumes, ports, networks и floating IP;
- evidence не содержит application credential secret, process environments и IP-адреса.

## Переменные stage

Уже используемые snapshot/deploy-контурами:

- `OS_AUTH_URL`;
- `OS_APPLICATION_CREDENTIAL_ID`;
- `OS_APPLICATION_CREDENTIAL_SECRET`;
- `OPENSTACK_SERVER_ID`.

## Последовательность приёмки

### 1. Выбрать source snapshot

Использовать image UUID из успешного `OpenStack Snapshot` artifact. Image должен оставаться в состоянии `active`.

### 2. Выполнить plan

Запустить `OpenStack Recovery Validation`:

- mode: `plan`;
- validation_name: например `aimeton-validation-recovery-001`;
- image_id: UUID snapshot;
- flavor: выбранный flavor name/UUID;
- network: выбранный network name/UUID;
- confirmation оставить пустым.

Ожидаемый результат: `validated_no_changes`.

### 3. Проверить стоимость и квоты

До `create` вручную подтвердить:

- доступную quota instances/cores/RAM;
- стоимость flavor и временного ресурса;
- отсутствие необходимости менять production DNS;
- допустимое временное окно;
- способ доступа к validation VM.

### 4. Создать validation VM

Повторить запуск с mode `create` и confirmation:

```text
CREATE aimeton-validation-recovery-001
```

Workflow ждёт `ACTIVE`, сохраняет UUID временной VM и sanitized evidence.

### 5. Провести функциональную проверку

Создание VM в состоянии `ACTIVE` является только инфраструктурной частью validation. Отдельно проверить:

- cloud-init/SSH или console access;
- загрузку ОС;
- Docker Engine и Compose;
- наличие ожидаемого `/opt/aimeton/auditor-stack`;
- запуск `aimeton-auditor`, Caddy, SearXNG и Valkey;
- `/api/health`;
- MCP initialize;
- соответствие критических данных и конфигурации;
- фактический RTO;
- фактическую точку восстановления/RPO.

Не переключать production/stage DNS на validation VM.

### 6. Зафиксировать evidence

В Issue #35 добавить:

- source image UUID;
- validation server UUID;
- timestamps начала и готовности;
- результаты OS/Docker/health/MCP;
- RTO и RPO;
- найденные расхождения;
- итог PASS/FAIL.

Secrets, IP-адреса и содержимое пользовательских данных не публиковать.

### 7. Удалить временную VM

После отдельного подтверждения запустить mode `delete`:

```text
DELETE <validation_server_id>
```

Удаляется только сервер с совпавшими UUID, именем и префиксом `aimeton-validation-`.

## Критерий закрытия Issue #35

Issue закрывается только если:

1. рабочая VM не изменялась;
2. validation VM создана из snapshot;
3. ОС и прикладной stack восстановились;
4. health/MCP прошли;
5. критические данные проверены;
6. RTO/RPO измерены;
7. временная VM контролируемо удалена;
8. recovery runbook обновлён фактическими результатами.
