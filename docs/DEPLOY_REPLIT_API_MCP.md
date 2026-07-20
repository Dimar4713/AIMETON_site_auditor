# Развёртывание AIMETON Site Auditor на Replit

## 1. Импорт

Импортируйте репозиторий и выберите ветку:

```text
experiment/dynamic-site-rendering
```

## 2. Secrets

Обязательные для полного режима:

```text
ROUTERAI_API_KEY=...
SEARXNG_BASE_URL=https://...
```

Дополнительные:

```text
ROUTERAI_MODEL=...
```

Без `ROUTERAI_API_KEY` анализ сайта переключается на локальные эвристики.
Без `SEARXNG_BASE_URL` анализ официального сайта работает, но внешний новостной и OSINT-контур возвращает статус `partial`.

## 3. Установка и запуск

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5000}
```

Файл `.replit` уже содержит эту команду.

## 4. Рабочие адреса

После публикации замените `YOUR-APP.replit.app` на домен приложения.

- UI: `https://YOUR-APP.replit.app/`
- Swagger/OpenAPI: `https://YOUR-APP.replit.app/docs`
- Health: `https://YOUR-APP.replit.app/api/health`
- MCP Streamable HTTP: `https://YOUR-APP.replit.app/mcp`

## 5. API компании

```bash
curl -X POST "https://YOUR-APP.replit.app/api/company-intelligence" \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Sib Dental Clinic",
    "url": "https://sibdentalclinic.ru",
    "region": "Красноярск",
    "max_sources": 20
  }'
```

Ответ содержит:

- анализ официального сайта;
- найденные источники с типом и уровнем доказательности;
- информационный запах;
- коммерческий балл;
- рекомендуемое решение;
- статус `complete` или `partial`;
- честный перечень неполноты и ошибок источников.

## 6. MCP-инструменты

MCP-сервер публикует три инструмента:

### `analyze_site`

Параметры:

```json
{"url":"https://example.ru"}
```

### `hunt_companies`

Параметры:

```json
{
  "region":"Красноярск",
  "industries":["стоматология"],
  "focus":["первичная консультация", "возврат клиентов"],
  "output_limit":10
}
```

### `company_intelligence`

Параметры:

```json
{
  "company_name":"Sib Dental Clinic",
  "url":"https://sibdentalclinic.ru",
  "region":"Красноярск",
  "max_sources":20
}
```

Используется стабильная линия официального Python SDK MCP `mcp>=1.25,<2` и транспорт Streamable HTTP.

## 7. Проверка после публикации

```bash
curl https://YOUR-APP.replit.app/api/health
```

Ожидается:

```json
{
  "status":"ok",
  "version":"0.4.0",
  "api":"/docs",
  "mcp":"/mcp"
}
```

Затем выполните тест `POST /api/company-intelligence`.

Для проверки MCP используйте MCP Inspector или клиента с поддержкой Streamable HTTP, указав:

```text
https://YOUR-APP.replit.app/mcp
```

## 8. Ограничения первой рабочей версии

- SearXNG используется как поисковый шлюз, а не как доказательство факта.
- Источники классифицируются эвристически; следующий этап — адаптеры конкретных реестров и СМИ.
- Отзывы и вакансии маркируются как слабые сигналы.
- Медицинские, финансовые и юридические выводы требуют проверки человеком.
- MCP пока не защищён отдельной авторизацией; до публичного широкого использования нужно добавить API-key/OAuth и лимиты запросов.
