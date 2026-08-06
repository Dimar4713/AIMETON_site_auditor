# AIMETON Time — входная инструкция

Перед любой операцией, где время является фактом, порядком событий, TTL, evidence или условием принятия решения, участник или агент MUST брать время из AIMETON Runtime Time.

## REST

```http
GET https://stage-auditor.aimeton.ru/api/runtime/time
GET https://stage-auditor.aimeton.ru/api/runtime/time/health
```

## MCP

```text
Endpoint: https://stage-auditor.aimeton.ru/mcp/
Tool: runtime.time
Arguments: {}
Transport: Streamable HTTP
Mode: stateless
```

Последовательность MCP:

```text
initialize
→ notifications/initialized
→ tools/list
→ tools/call runtime.time {}
```

Отсутствие `Mcp-Session-Id` допустимо: stage использует `stateless_http=True`.

## Trust gates

Использовать ответ разрешено только когда:

```text
source == chrony
synced == true
quality == trusted
abs(offset_ms) <= 50
stratum <= 4
utc заканчивается на Z
```

Иначе действовать fail-closed:

```text
blocked:untrusted_time
```

Не подменять AIMETON Time часами модели, браузера, runner, контейнера, ноутбука или внешнего сервиса.

## Форматы

Машинный формат:

```text
YYYY-MM-DDTHH:MM:SS.sssZ
```

Строка operational status:

```text
YYYY-MM-DD HH:MM UTC — сообщение
```

## Где обязательно

- mission events и heartbeat;
- logs, incident и audit trail;
- acceptance/evidence artifacts;
- deployment, backup, restore и persistence checks;
- freshness, TTL, timeout и ordering;
- межагентный handoff;
- фактические timestamps отчётов.

## Подтверждённая live-приёмка

```text
Workflow: 31102018159
SHA: 4b84c27a3594c097ba88db4e130a459ca99dbdaf
Artifact digest: sha256:160b2a4c5ad0d1e142cc809340877cb593783770bfe20962842c555b7857702c
MCP result: source=chrony, synced=true, quality=trusted, stratum=2, offset_ms=0.007769
```

Нормативный полный контракт:

```text
Dimar4713/aimeton-architecture/docs/operations/AIMETON_TIME_ACCESS.md
```

> Не угадывай время. Запроси AIMETON Time и проверь доверие.