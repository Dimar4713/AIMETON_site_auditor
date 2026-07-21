# SA-01.7 — Регрессионный пакет KIMI

## Назначение

Пакет закрепляет воспроизводимыми тестами дефекты и ожидаемые свойства, выявленные в ходе внешнего тестирования KIMI. Он не обращается к реальным поисковым сервисам, не содержит секретов и запускается обычным `pytest` в Baseline CI.

## Карта дефектов и тестов

| Кейс | Риск / прежний дефект | Контроль |
|---|---|---|
| KIMI-SEARCH-01 | повторный запуск внешнего поиска | `test_company_intelligence_calls_external_provider_once_and_stays_partial_without_evidence` и существующий single-search regression |
| KIMI-CLASS-01 | `query_kind` подменяет класс источника | `KIMI-CLASS-NEWS-JOBS` |
| KIMI-CLASS-02 | суд, официальный сайт и unknown классифицируются не по фактическим признакам | golden cases COURT / OFFICIAL / UNKNOWN |
| KIMI-EVIDENCE-01 | поисковый сниппет становится доказательством | `test_search_hint_is_not_evidence_by_default` и lifecycle regression |
| KIMI-PRESCORE-01 | отсутствующие данные маскируются нулём | `KIMI-PRESCORE-UNKNOWN` |
| KIMI-PRESCORE-02 | порядок кандидатов не объясним | `KIMI-PRESCORE-HIGH` и отдельные threshold tests SA-01.6 |
| KIMI-COMPLETE-01 | одни поисковые подсказки дают статус complete | runtime test с `discovery_hint` и ожидаемым `partial` |
| KIMI-MCP-01 | stage redirect / host-origin regression | существующие `test_mcp_*` baseline-тесты |

## Runtime tests и golden cases

### Runtime tests

Проверяют исполняемые свойства:

- число вызовов provider;
- отсутствие повышения evidence status;
- статус полноты результата;
- запрет deep processing до pre-score.

### Golden cases

`tests/fixtures/kimi_regression_cases.json` содержит только стабильные входы и ожидаемые классификационные или числовые результаты. Golden cases не выполняют сеть и не зависят от времени.

## Правила изменения golden outputs

Изменение ожидаемого результата допустимо только одновременно с:

1. изменением нормативного правила или классификатора;
2. обновлением `schema_version` fixture-файла;
3. описанием причины в PR;
4. подтверждением, что изменение не возвращает известный дефект.

Нельзя обновлять golden output только для того, чтобы сделать CI зелёным.

## Обоснованные исключения

Реальные ответы KIMI, RouterAI, SearXNG и внешних сайтов не фиксируются побитово: они нестабильны и могут содержать закрытые данные. Вместо этого тестируются наши контракты, переходы состояний и решения на детерминированных fixtures.
