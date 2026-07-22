# Guarded OpenStack snapshot workflow

## Назначение

Workflow `OpenStack Snapshot` создаёт image snapshot канонического сервера `aimeton-main-server` через Nova `createImage`, затем ожидает состояние `active` через Glance.

Это отдельный аварийно-инфраструктурный контур. Он не запускается автоматически при обычном deployment.

## Защитные ограничения

- запуск только вручную через `workflow_dispatch`;
- GitHub Environment: `stage`;
- точный UUID сервера нужно ввести повторно;
- причина должна быть осмысленной и не короче 8 символов;
- имя snapshot формируется только с префиксом `aimeton-main-server-`;
- перед write-вызовом проверяются UUID, имя и статус `ACTIVE`;
- существующие images/snapshots не удаляются;
- сервер, тома, сеть и порты не изменяются;
- reboot, rebuild и delete отсутствуют;
- основной пароль OpenStack не используется.

## Запуск

1. Открыть `Actions → OpenStack Snapshot → Run workflow`.
2. В `confirm_server_id` ввести канонический UUID сервера из Environment Variable `OPENSTACK_SERVER_ID`.
3. В `reason` указать конкретную причину, например `before controlled network change`.
4. В `snapshot_suffix` указать короткий идентификатор: `before-network-change`.
5. Запустить workflow.

## Результат

После успеха workflow формирует artifact `openstack-snapshot-<run_id>` со следующими данными:

- actor;
- UTC timestamp;
- причина;
- project ID и user ID;
- server UUID, имя и статус;
- image UUID, имя, статус, размер и время создания;
- OpenStack request IDs;
- GitHub workflow context.

Secrets в artifact не записываются.

## Восстановление

Создание snapshot не означает автоматический rollback. Восстановление выполняется отдельной контролируемой процедурой после проверки:

1. исходная VM недоступна или признана повреждённой;
2. snapshot имеет статус `active`;
3. зафиксированы server UUID и image UUID;
4. определён способ восстановления: новая VM из image либо отдельный rebuild-процесс;
5. подтверждены сеть, security groups, volume layout, DNS и rollback window.

Автоматический `rebuild` текущей VM запрещён до отдельного workflow и отдельного теста.

## Retention

До отдельного решения snapshots не удаляются автоматически. Перед включением retention policy необходимо определить:

- максимально допустимое количество images;
- стоимость хранения;
- минимальный срок хранения;
- protected snapshots;
- правила ручного подтверждения удаления.
