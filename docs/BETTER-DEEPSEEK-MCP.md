# Better DeepSeek ↔ AIMETON MCP

## Назначение

Этот документ фиксирует поддерживаемый браузерный путь подключения Better DeepSeek к публичному read-only MCP AIMETON Site Auditor.

Канонический stage endpoint:

```text
https://stage-auditor.aimeton.ru/mcp/
```

Better DeepSeek выполняет MCP discovery из браузерного origin:

```text
https://chat.deepseek.com
```

## Почему нужен отдельный browser contract

MCP transport security и browser CORS решают разные задачи.

1. FastMCP transport security проверяет `Host` и `Origin` и защищает от DNS rebinding / неподтверждённых origins.
2. Браузер дополнительно выполняет CORS preflight и не отдаёт JavaScript ответ, если сервер не вернул разрешающие CORS headers.

Поэтому browser MCP считается рабочим только когда проходят оба слоя.

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

Для явно разрешённого browser origin public MCP поддерживает:

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
- `X-Request-ID`.

В browser response экспонируются:

- `MCP-Session-Id`;
- `X-Request-ID`.

Неизвестный browser origin должен получать отказ. Wildcard origins запрещены.

Дополнительные browser origins могут быть явно добавлены через:

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
2. выполнить MCP discovery;
3. убедиться, что отсутствует `403 Invalid Origin header`;
4. убедиться, что доступен `runtime.time`;
5. убедиться, что доступен `analyze_site`;
6. вызвать `runtime.time` и получить нормальный MCP result;
7. проверить, что неизвестный Origin по-прежнему отклоняется;
8. проверить, что `/mcp-admin/` не получил browser CORS-доступ.

## Отдельные ошибки статуса DeepSeek

Сообщения браузерной консоли вида:

```text
Failed to fetch server status
status.deepseek.com ... blocked by CORS policy
hif-dliq.deepseek.com ... ERR_NAME_NOT_RESOLVED
```

не являются тем же отказом, что AIMETON MCP `403 Invalid Origin header`.

Они относятся к отдельной функции Better DeepSeek/DeepSeek, которая проверяет внешние status endpoints. Диагностику MCP следует вести по сообщениям `MCP discovery failed` и по `X-Request-ID` AIMETON.

## Принцип расширения

Новые браузерные AI-клиенты не получают wildcard-доступ. Для каждого клиента:

1. фиксируется точный HTTPS origin;
2. добавляется regression test;
3. public/admin boundary проверяется отдельно;
4. после deployment выполняется browser-level acceptance;
5. широкие GitHub, SSH, provider и production credentials клиенту не передаются.
