# Benchmark поиска клиентов — Красноярск / Стоматология

Дата прогона: **2026-08-09 UTC**  
Репозиторий: `Dimar4713/AIMETON_site_auditor`  
Связанная проблема провайдеров: **Issue #493**  
Workflow evidence: **Search Strategy Snapshot Replay Benchmark #1**, run `31292210367`.

## Цель

Сравнить все 10 стратегий `SearchGateway` на одном логическом запросе:

`Красноярск ; Стоматология`

Для устойчивости использованы 8 фиксированных поисковых вариантов. Методика и формула score были зафиксированы до итогового ранжирования.

## Провайдеры этого валидного прогона

- **Tavily** — live snapshot с GitHub-hosted egress: 130 raw results на 8 запросов; моделируемая стоимость `$0.064` при `$0.008/call`.
- **SearXNG** — live snapshot со Stage: 80 raw results на 8 запросов; маржинальная API-стоимость `0`.
- **Yandex Search** — не включён в итоговый рейтинг: текущий Stage `YANDEX_CLOUD_FOLDER_ID` повреждён/non-ASCII и Yandex возвращает `Permission denied`. Финальный трёхпровайдерный benchmark должен быть повторён после восстановления канонического Folder ID.

## Автоматический рейтинг

| Rank | Strategy | Score | Heuristic direct domains | Precision | Benchmark recall | Regional recall | Corroboration | Time | Tavily calls | SearXNG calls | Cost USD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `consensus_union` | 73.42 | 77 | 63.6% | 100.0% | 100.0% | 9.1% | 17.39 s | 8 | 8 | 0.064 |
| 2 | `parallel_union` | 73.29 | 77 | 63.6% | 100.0% | 100.0% | 7.8% | 17.39 s | 8 | 8 | 0.064 |
| 3 | `exhaustive_coverage` | 73.05 | 77 | 63.6% | 100.0% | 100.0% | 7.8% | 19.18 s | 8 | 8 | 0.064 |
| 4 | `adaptive_cost_quality` | 73.05 | 77 | 63.6% | 100.0% | 100.0% | 7.8% | 19.18 s | 8 | 8 | 0.064 |
| 5 | `cascade_until_target` | 73.05 | 77 | 63.6% | 100.0% | 100.0% | 7.8% | 19.18 s | 8 | 8 | 0.064 |
| 6 | `sequential_union` | 73.05 | 77 | 63.6% | 100.0% | 100.0% | 7.8% | 19.18 s | 8 | 8 | 0.064 |
| 7 | `fallback_first_nonempty` | 70.92 | 66 | 79.5% | 85.7% | 80.0% | 0.0% | 17.38 s | 8 | 0 | 0.064 |
| 8 | `primary_only` | 70.92 | 66 | 79.5% | 85.7% | 80.0% | 0.0% | 17.38 s | 8 | 0 | 0.064 |
| 9 | `shadow_compare` | 70.69 | 66 | 79.5% | 85.7% | 80.0% | 0.0% | 19.18 s | 8 | 8 | 0.064 |
| 10 | `split_query_routing` | 54.95 | 46 | 63.0% | 59.7% | 66.0% | 6.5% | 10.58 s | 4 | 4 | 0.032 |

Формула score: **50% recall + 35% precision + 10% corroboration + 5% time/cost efficiency**.

## Более строгая проверка локальных клиник

Автоматический классификатор дал объединение из 77 probable direct-company domains. Дополнительная более строгая проверка evidence оставила **40 вероятных локальных стоматологических доменов**:

- Tavily: **32**;
- SearXNG: **14**;
- пересечение: **6**;
- объединение: **40**.

По этой строгой выборке:

- full-union/cascade/consensus/parallel/adaptive/exhaustive: **40/40 = 100%**;
- Tavily-only effective modes: **32/40 = 80%**;
- `split_query_routing`: **29/40 = 72.5%**.

Это benchmark recall относительно найденного корпуса, **не абсолютная доля всего рынка Красноярска**.

## Состав evidence

- `benchmark.json` — структурированный итог всех 10 стратегий;
- `summary.md` — исходный markdown-отчёт harness;
- `replay.log` — журнал полного replay;
- `tavily-snapshot.zip` — live Tavily snapshot;
- `searxng-snapshot.zip` — live SearXNG snapshot;
- `two-provider-replay.zip` — исходный Actions artifact с `benchmark.json`, `summary.md`, `replay.log`;
- `SHA256SUMS.txt` — контрольные суммы машинного evidence.

## Ограничение / следующий шаг

Это канонический evidence **двухпровайдерного** сравнения. Он не должен трактоваться как окончательный рейтинг Tavily + Yandex + SearXNG. После восстановления корректного Yandex Cloud Folder ID требуется повторить тот же benchmark без изменения методики и добавить трёхпровайдерный evidence рядом с этим набором.
