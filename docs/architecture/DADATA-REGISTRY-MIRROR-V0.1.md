# DaData Registry Mirror v0.1

## Назначение

DaData используется как временный автоматический источник предварительной проверки идентичности компании до появления прямого production-доступа к официальной выгрузке ФНС.

Это **registry mirror**, а не официальный реестр. Ни один ответ DaData не может устанавливать `authority_verified=true`.

## Конфигурация

Runtime читает секреты только из переменных окружения:

- `DADATA_API` — API-ключ для `Authorization: Token ...`;
- `DADATA_SECRET` — сохранён для совместимости с другими API DaData, но метод `findById/party` его не передаёт.

Значения секретов не возвращаются в health, API-ответах и логических моделях.

## Маршруты

Поскольку router Entity Resolution имеет prefix `/api/missions`, доступны:

- `GET /api/missions/registry-mirror/dadata/health`;
- `POST /api/missions/registry-mirror/dadata/find-party`.

Тело lookup-запроса:

```json
{
  "query": "7707083893"
}
```

## Семантика доверия

- exact match по ИНН или ОГРН → `registry_mirror_verified`;
- отсутствие результата → `unresolved`;
- несколько различающихся exact records → `conflicting`;
- отсутствующий ключ → `unavailable`;
- во всех состояниях `authority_verified=false`;
- gap `official_registry_verification` сохраняется до получения подписанной выписки или прямого feed ФНС.

## Доказательность

Для каждой записи сохраняются:

- provider и source URL;
- время доступа;
- query;
- SHA-256 digest нормализованного provider payload;
- ИНН, КПП, ОГРН, юридическое имя;
- тип субъекта, branch type, статус и дата актуальности;
- внутренний `hid`, но не API-ключи.

## Экономия запросов

Provider использует in-memory cache с TTL 24 часа. Повторный запрос по тому же идентификатору в пределах TTL не вызывает DaData повторно.

Для production после появления нескольких реплик приложения cache должен быть перенесён в Valkey с тем же интерфейсом и ключом, не меняя contract API.

## Следующий срез

1. передать `DADATA_API` и `DADATA_SECRET` из deployment secret store в контейнер stage;
2. выполнить live smoke по тестовому ИНН без вывода headers;
3. связать `registry_mirror_verified` с выбранным `IdentityCandidate` и human-review queue;
4. добавить ручную загрузку подписанной PDF-выписки ФНС как официальный authority gate.
