# Красноярск / Стоматология — трёхдвижковый Search Gateway benchmark

Дата: 2026-08-09 UTC  
Workflow run: `31295273972`  
Harness commit: `9148a831890a69e02b85244d59e8f5ad62e40305`

## Цель

Сравнить все 10 реально реализованных стратегий AIMETON Search Gateway на одном и том же сценарии поиска клиентов: `Красноярск ; Стоматология`.

Использованы одинаковые 8 query-вариантов и live-снимки трёх поисковых движков:

- Yandex Search — live snapshot через GitHub-hosted egress;
- Tavily — live snapshot через GitHub-hosted egress;
- SearXNG — live snapshot с Stage AIMETON.

Все 10 стратегий затем исполнялись настоящим `SearchGateway` AIMETON на фиксированных снимках. Это устраняет влияние изменения web-выдачи между режимами и позволяет сравнивать именно executor-стратегии.

## Live input

- Yandex: 8 вызовов, 160 raw results, модельная стоимость `0.08 RUB`.
- Tavily: 8 вызовов, 110 raw results, модельная стоимость `$0.064`.
- SearXNG: self-hosted, нулевая маржинальная API-стоимость.

## Рейтинг

Формула score была задана заранее: `50% recall + 35% precision + 10% corroboration + 5% time/cost efficiency`.

| Место | Стратегия | Score | Direct domains | Precision | Recall | Regional recall | Corroboration | Время, с | Вызовы Y/T/S | RUB | USD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | `consensus_union` | 76.38 | 71 | 68.9% | 94.7% | 92.2% | 38.0% | 17.52 | 8/8/8 | 0.08 | 0.064 |
| 2 | `exhaustive_coverage` | 75.36 | 75 | 66.4% | 100.0% | 96.9% | 21.3% | 31.70 | 8/8/8 | 0.08 | 0.064 |
| 3 | `adaptive_cost_quality` | 75.25 | 67 | 78.8% | 89.3% | 90.6% | 28.4% | 29.67 | 8/8/5 | 0.08 | 0.064 |
| 4 | `parallel_union` | 74.99 | 67 | 77.9% | 89.3% | 87.5% | 19.4% | 17.52 | 8/8/8 | 0.08 | 0.064 |
| 5 | `cascade_until_target` | 74.10 | 67 | 77.9% | 89.3% | 87.5% | 19.4% | 28.83 | 8/8/4 | 0.08 | 0.064 |
| 6 | `sequential_union` | 73.87 | 67 | 77.9% | 89.3% | 87.5% | 19.4% | 31.69 | 8/8/8 | 0.08 | 0.064 |
| 7 | `fallback_first_nonempty` | 64.78 | 47 | 87.0% | 62.7% | 65.6% | 0.0% | 9.72 | 8/0/0 | 0.08 | 0 |
| 8 | `primary_only` | 64.78 | 47 | 87.0% | 62.7% | 65.6% | 0.0% | 9.72 | 8/0/0 | 0.08 | 0 |
| 9 | `shadow_compare` | 62.20 | 47 | 87.0% | 62.7% | 65.6% | 0.0% | 26.52 | 8/8/8 | 0.08 | 0.064 |
| 10 | `split_query_routing` | 56.20 | 37 | 71.2% | 49.3% | 54.7% | 35.1% | 11.97 | 3/3/2 | 0.03 | 0.024 |

Reference union benchmark: 75 probable direct-company domains; regional subset: 64.

## Выводы

1. `consensus_union` — лучший общий баланс качества, полноты и междвижкового подтверждения.
2. `exhaustive_coverage` — максимальная полнота: 75/75 reference domains, но дольше и с меньшей precision.
3. `parallel_union` — почти тот же полезный охват, но заметно быстрее последовательного объединения.
4. `adaptive_cost_quality` — самая высокая precision среди полноохватных режимов (78.8%) и хорошая полнота.
5. `primary_only` / `fallback_first_nonempty` экономны и точны, но теряют около 37% доступного reference corpus.
6. `split_query_routing` дешевле, но теряет более половины reference recall и не подходит для задачи «максимально найти рынок».
7. `shadow_compare` остаётся внутренним диагностическим/A-B режимом, а не клиентским режимом выдачи.

## Важное эксплуатационное наблюдение

Актуальные Yandex credentials и `YANDEX_CLOUD_FOLDER_ID=b1gs950eottalhsc8rt2` подтверждены рабочими: GitHub-hosted Yandex snapshot успешно получил 20 результатов для каждого из 8 запросов.

При этом тот же Yandex runtime со Stage VPS получает HTTP 403 `Permission denied`. Tavily ранее показал такую же egress-зависимость: тот же token работает с GitHub-hosted runner и блокируется со Stage VPS. Поэтому текущий P1 — не восстановление ключей, а разбор/смена outbound egress Stage для внешних поисковых providers.

Это не искажает сравнительный benchmark: live provider snapshots сняты там, где providers успешно отвечают, а стратегии исполнялись одинаковым SearchGateway AIMETON на фиксированном corpus.

## Артефакты

В этом каталоге должны находиться:

- `yandex-snapshot.zip` — точный Actions artifact Yandex;
- `tavily-snapshot.zip` — точный Actions artifact Tavily;
- `searxng-snapshot.zip` — точный Actions artifact SearXNG;
- `three-provider-replay.zip` — точный comparative replay artifact;
- `benchmark.json` — структурированные результаты всех 10 стратегий;
- `summary.md` — автоматически сформированная таблица и top domains;
- `replay.log` — полный replay log;
- `SHA256SUMS.txt` — контрольные суммы durable evidence.

Provider-access follow-up: Issue #493.
