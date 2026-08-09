# Красноярск / Стоматология — current Stage Search Gateway benchmark

Дата: 2026-08-09 UTC
Workflow run: `31301705371`
Stage application SHA: `1bcc6cee231b02d00fd53815e97243d83e2764bf`
Benchmark harness commit: `c0188706208153f5fe856bc16a78950941b1dcf2`

## Цель

Повторно сравнить все 10 реализованных стратегий AIMETON Search Gateway на сценарии `Красноярск ; Стоматология` после доработки provider eligibility/contract gate.

## Методика и происхождение входов

Одинаковые 8 query-вариантов использованы для всех стратегий.

- **Yandex Search:** свежий live snapshot непосредственно из Stage-контейнера — 8 вызовов, 160 raw results, стоимость `0.08 RUB`.
- **SearXNG:** свежий live snapshot непосредственно из Stage — 8 запросов, 86 raw results, нулевая маржинальная API-стоимость.
- **Tavily:** переиспользован ранее зафиксированный live snapshot — 8 запросов, 110 raw results, историческая стоимость получения `$0.064`. В этом повторном Stage-run новых Tavily API-вызовов не было; `TAVILY_CONTRACT_ALLOWED=false`.

Все 10 executor-стратегий исполнялись настоящим текущим `SearchGateway` внутри Stage-контейнера на одном фиксированном корпусе. Формула score была задана заранее: `50% recall + 35% precision + 10% corroboration + 5% time/cost efficiency`.

## Рейтинг

Reference union: **76 probable direct-company domains**, regional subset: **66**.

| Место | Стратегия | Score | Direct | Precision | Recall | Regional recall | Corroboration | Время, с | Y/T/S | RUB | USD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | `exhaustive_coverage` | 77.23 | 76 | 71.0% | 100.0% | 98.5% | 23.7% | 26.20 | 8/8/8 | 0.08 | 0.064 |
| 2 | `consensus_union` | 75.39 | 70 | 70.0% | 92.1% | 89.4% | 38.6% | 15.95 | 8/8/8 | 0.08 | 0.064 |
| 3 | `adaptive_cost_quality` | 73.24 | 62 | 80.5% | 81.6% | 89.4% | 37.1% | 22.02 | 8/7/7 | 0.08 | 0.056 |
| 4 | `parallel_union` | 72.77 | 64 | 79.0% | 84.2% | 81.8% | 20.3% | 15.95 | 8/8/8 | 0.08 | 0.064 |
| 5 | `cascade_until_target` | 72.27 | 64 | 79.0% | 84.2% | 81.8% | 20.3% | 21.18 | 8/8/4 | 0.08 | 0.064 |
| 6 | `sequential_union` | 71.79 | 64 | 79.0% | 84.2% | 81.8% | 20.3% | 26.20 | 8/8/8 | 0.08 | 0.064 |
| 7 | `fallback_first_nonempty` | 62.46 | 44 | 86.3% | 57.9% | 60.6% | 0.0% | 4.56 | 8/0/0 | 0.08 | 0 |
| 8 | `primary_only` | 62.46 | 44 | 86.3% | 57.9% | 60.6% | 0.0% | 4.56 | 8/0/0 | 0.08 | 0 |
| 9 | `split_query_routing` | 61.09 | 40 | 81.6% | 52.6% | 59.1% | 30.0% | 8.99 | 3/3/2 | 0.03 | 0.024 |
| 10 | `shadow_compare` | 59.69 | 44 | 86.3% | 57.9% | 60.6% | 0.0% | 20.51 | 8/8/8 | 0.08 | 0.064 |

## Стоимость

Инкрементальная стоимость именно run `31301705371`: Yandex `0.08 RUB`; SearXNG `$0`; новых Tavily расходов `$0`. Таблица сохраняет модельную стоимость стратегии так, как если бы соответствующий Tavily corpus получался live: полноохватные режимы `0.08 RUB + $0.064`, adaptive `0.08 RUB + $0.056`, split `0.03 RUB + $0.024`.

## Интерпретация

`Precision` и `Recall` — benchmark-метрики относительно heuristic direct-company classification и объединённого reference corpus, а не абсолютная доля всех реально существующих клиник Красноярска. Один домен может представлять несколько филиалов.

## Артефакты

`benchmark.json`, `summary.md`, `replay.log`, `input-provenance.json`, свежие `yandex-current.json` и `searxng-current.json`, переиспользованный `tavily-snapshot.zip`, точный `current-stage-benchmark.zip` и `SHA256SUMS.txt`.
