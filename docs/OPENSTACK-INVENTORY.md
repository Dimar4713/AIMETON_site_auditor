# OpenStack inventory for immers.cloud

## Назначение

Первый слой SA-02.2 — только чтение фактического состояния проекта OpenStack: серверы, адреса, тома, сетевые порты и security groups.

Скрипт `scripts/openstack_inventory.py` не содержит операций create, update, delete, reboot, rebuild, rescue или snapshot.

## Аутентификация

Использовать OpenStack Application Credential, а не основной пароль пользователя.

Обязательные переменные окружения:

```bash
export OS_AUTH_URL=https://api.immers.cloud:5000/v3
export OS_AUTH_TYPE=v3applicationcredential
export OS_APPLICATION_CREDENTIAL_ID=...
export OS_APPLICATION_CREDENTIAL_SECRET=...
```

Опционально:

```bash
export OS_REGION_NAME=...
```

Секрет нельзя сохранять в репозитории, shell history, Actions artifacts или открытых логах.

## Установка

```bash
python3 -m venv .venv-openstack
source .venv-openstack/bin/activate
pip install -r requirements-openstack.txt
```

## Запуск

```bash
python scripts/openstack_inventory.py
```

Сохранение JSON:

```bash
python scripts/openstack_inventory.py --output openstack-inventory.json
```

## Правила безопасности

- endpoints получаются через Keystone service catalog;
- TLS verification включена;
- основной пароль OpenStack не используется;
- inventory запускается read-only;
- destructive operations по умолчанию отсутствуют;
- JSON inventory может содержать IP, UUID и metadata, поэтому не должен публиковаться как публичный artifact.

## Следующее расширение

После проверки inventory:

1. закрепить UUID `aimeton-main-server`;
2. добавить preflight статуса VM перед deployment;
3. добавить snapshot workflow с явным подтверждением;
4. добавить guarded soft reboot;
5. описать rescue/recovery без автоматического rebuild.
