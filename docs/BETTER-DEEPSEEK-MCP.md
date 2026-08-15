# Better DeepSeek ↔ AIMETON MCP

## Назначение

Этот документ фиксирует поддерживаемый браузерный путь подключения Better DeepSeek к публичному read-only MCP AIMETON Site Auditor.

Канонический stage endpoint:

```text
https://stage-auditor.aimeton.ru/mcp/
```

## Фактический Origin Better DeepSeek

Better DeepSeek показывает UI внутри `https://chat.deepseek.com`, но MCP HTTP-запросы выполняет не page context, а background service worker расширения.

Поэтому для официальной Chrome Web Store сборки транспортный Origin:

```text
chrome-extension://aabiopennjmopfippagcalmkdjlepdhh
```

Официальный Chrome Web Store ID зафиксирован в upstream Better DeepSeek README.

`https://chat.deepseek.com` также остаётся разрешённым для возможных page-context вызовов, но не является основным Origin встроенной кнопки MCP `Test`.

Для unpacked/dev-сборки Chrome ID может отличаться. Такой ID не получает wildcard-доступ и должен добавляться оператором явно через `AIMETON_MCP_BROWSER_ORIGINS`.

## Почему нужен отдельный browser contract

MCP transport security и browser CORS решают разные задачи.

1. FastMCP transport security проверяет `Host` и `Origin` и защищает от DNS rebinding / неподтверждённых origins.
2. Браузер или extension runtime может дополнительно применять CORS/preflight требования в зависимости от контекста и host permissions.

Поэтому browser/extension MCP считается рабочим только когда проходит транспортный allowlist и, где требуется, CORS слой.

## Разрешённый профиль

Better DeepSeek подключается только к public MCP profile.

Public profile остаётся:

- read-only;
- без admin credentials;
- rate-limited;
- concurrency-limited;
- с явным host/origin allowlist;
- с санитарно очищенным audit trail.

`/mcp-admin/` не публикует browser CORS для Better DeepSeek и не должен добавляться в настройки браузерного клиента.

## CORS contract

Для явно разрешённого browser/extension origin public MCP поддерживает:

- `GET`;
- `POST`;
- `DELETE`;
- `OPTIONS` preflight.

Разрешённые MCP/browser headers включают:

- `Accept`;
- `Authorization`;
- `Content-Type`;
- `Last-Event-ID`;
- `MCP-Protocol-Version`;
- `MCP-Session-Id`;
- `X-API-Key`;
- `X-Request-ID`.

В browser response экспонируются:

- `MCP-Session-Id`;
- `X-Request-ID`.

Неизвестный browser/extension origin должен получать отказ. Wildcard origins запрещены.

Дополнительные browser origins могут быть явно добавлены через:

```text
AIMETON_MCP_BROWSER_ORIGINS=chrome-extension://<explicit-extension-id>
```

или, для обычного web client:

```text
AIMETON_MCP_BROWSER_ORIGINS=https://client.example
```

Значения с `*` игнорируются.

## Настройка Better DeepSeek

Добавить MCP server:

```text
Name: AIMETON Site Auditor RO
URL: https://stage-auditor.aimeton.ru/mcp/
Transport: Streamable HTTP
Credentials: none
```

Admin endpoint и admin bearer token в Better DeepSeek не добавлять.

## Acceptance

После deployment:

1. открыть `https://chat.deepseek.com` с Better DeepSeek;
2. нажать встроенную кнопку MCP `Test`;
3. убедиться, что отсутствует `403 Invalid Origin header`;
4. убедиться, что обнаружены инструменты;
5. убедиться, что доступен `runtime.time`;
6. убедиться, что доступен `analyze_site`;
7. вызвать `runtime.time` и получить нормальный MCP result;
8. проверить, что неизвестный `chrome-extension://...` Origin по-прежнему отклоняется;
9. проверить, что `/mcp-admin/` не получил browser CORS-доступ.

## Отдельные ошибки статуса DeepSeek

Сообщения браузерной консоли вида:

```text
Failed to fetch server status
status.deepseek.com ... blocked by CORS policy
hif-dliq.deepseek.com ... ERR_NAME_NOT_RESOLVED
```

не являются тем же отказом, что AIMETON MCP `403 Invalid Origin header`.

Они относятся к отдельной функции Better DeepSeek/DeepSeek, которая проверяет внешние status endpoints. Диагностику MCP следует вести по сообщениям `MCP discovery failed`, встроенному MCP `Test` и по `X-Request-ID` AIMETON.

## Принцип расширения

Новые браузерные AI-клиенты и расширения не получают wildcard-доступ. Для каждого клиента:

1. фиксируется точный web/extension origin;
2. добавляется regression test;
3. public/admin boundary проверяется отдельно;
4. после deployment выполняется browser-level acceptance;
5. широкие GitHub, SSH, provider и production credentials клиенту не передаются.
