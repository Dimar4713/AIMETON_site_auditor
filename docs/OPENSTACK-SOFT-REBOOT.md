# OpenStack soft reboot

## Назначение

Workflow `OpenStack Soft Reboot` выполняет контролируемую мягкую перезагрузку канонической stage VM и проверяет восстановление приложения извне.

## Почему используется GitHub-hosted runner

Self-hosted runner размещён на самой `aimeton-main-server`. Во время reboot он станет недоступен и не сможет подтвердить восстановление. Поэтому операция выполняется на независимом `ubuntu-latest`.

## Guardrails

- запуск только вручную;
- Environment `stage`;
- точный UUID канонической VM;
- отдельная фраза `SOFT-REBOOT`;
- причина не короче 10 символов;
- preflight требует имя `aimeton-main-server` и статус `ACTIVE`;
- код поддерживает только Nova reboot type `SOFT`;
- hard reboot, rebuild, rescue, delete, stop/start отсутствуют;
- после reboot проверяются Nova `ACTIVE`, `/api/health = 200` и `/mcp = 307`;
- evidence хранится 90 дней.

## Запуск

`Actions → OpenStack Soft Reboot → Run workflow`.

Поля:

- `confirm_server_id`: `b880085c-a31f-4cd5-9ed5-e009000179e7`;
- `confirmation`: `SOFT-REBOOT`;
- `reason`: осмысленное описание окна и цели операции.

## Evidence

Artifact `openstack-soft-reboot-<run_id>` содержит:

- внешний preflight приложения;
- OpenStack evidence с actor, reason, timestamps, state history и request IDs;
- внешний postflight приложения.

Secrets в artifact не записываются.

## Ограничения

Workflow не является автоматическим recovery. Если soft reboot не восстановил VM или приложение, дальнейшие hard reboot, rescue, rebuild или восстановление из snapshot выполняются только отдельной процедурой с новым уровнем подтверждения.
