# AIMETON Search Gateway — стратегия движков и тарифные профили

## Цель

AIMETON располагает тремя независимыми поисковыми providers:

- `searxng` — self-hosted метапоиск;
- `yandex` — внешний Yandex Search provider;
- `tavily` — внешний Tavily provider.

Наличие нескольких providers не означает, что они обязаны вызываться одинаково. Search Gateway разделяет:

1. **provider inventory** — какие движки доступны;
2. **execution strategy** — как они используются совместно;
3. **tariff search profile** — какие ограничения и стратегия применяются к конкретному классу обслуживания;
4. **global owner policy** — жёсткие ограничения, которые тариф не может обойти.

## Каталог стратегий

| ID | Назначение | Охват | Стоимость | Статус |
|---|---|---|---|---|
| `primary_only` | один доступный provider | низкий/предсказуемый | минимальная | implemented |
| `fallback_first_nonempty` | последовательный fallback до первого непустого ответа | средний | низкая | implemented |
| `cascade_until_target` | объединять providers, пока не достигнут target уникальных результатов | высокий | управляемая | implemented |
| `sequential_union` | последовательно вызвать все разрешённые providers и объединить | высокий | средняя/высокая | implemented |
| `parallel_union` | параллельный fan-out и merge | высокий, меньшая latency | средняя/высокая | planned |
| `consensus_union` | union + усиление доменов, найденных несколькими providers | высокий + corroboration | высокая | planned |
| `split_query_routing` | разные LLM query variants распределяются между providers | высокий при меньшем fan-out | управляемая | planned |
| `adaptive_cost_quality` | динамический выбор по yield/latency/health/budget | адаптивный | оптимизируемая | planned |
| `exhaustive_coverage` | все allowed providers × все query variants в пределах hard caps | максимальный | максимальная | planned |
| `shadow_compare` | secondary providers работают только для benchmark, не меняя выдачу | диагностический | дополнительная | planned/internal |

`cache-first` является ортогональным поведением и не считается отдельной стратегией.

## Реализованные режимы

### primary_only
Используется первый доступный и разрешённый provider. Если он вернул пусто или ошибку, другие providers не вызываются после первой реальной попытки.

### fallback_first_nonempty
Текущая классическая схема отказоустойчивости: providers вызываются по порядку; первый непустой результат становится ответом.

### cascade_until_target
Результаты providers последовательно объединяются и дедуплицируются. Каскад останавливается, когда достигнут `target_results` или исчерпан `max_providers_per_query`.

### sequential_union
Все разрешённые providers вызываются последовательно до `max_providers_per_query`; результаты объединяются и дедуплицируются. Платный secondary fan-out требует отдельного разрешения и budget cap.

## Тарифные профили

Технические профили не являются ценовым обещанием и не определяют коммерческую стоимость подписки. До появления billing/account-plan binding один профиль выбирается глобально владельцем.

### Free
- strategy: `primary_only`;
- providers: только `searxng`;
- paid providers: запрещены;
- 8 query variants × 5 results/provider;
- candidate pool 40, output 15.

### Start
- strategy: `fallback_first_nonempty`;
- order: `searxng → yandex → tavily`;
- paid policy наследует действующую env-policy;
- 20 query variants × 10 results/provider;
- candidate pool 100, output 25.

### Pro
- strategy: `cascade_until_target`;
- target 40 unique results/query;
- up to 3 providers/query;
- 30 query variants × 15 results/provider;
- candidate pool 200, output 50;
- paid fan-out отдельно защищён policy + budget.

### Max
- strategy: `sequential_union`;
- target 75 unique results/query;
- up to 3 providers/query;
- 50 query variants × 20 results/provider;
- candidate pool 400, output 100;
- paid fan-out отдельно защищён policy + budget.

## Глобальная политика владельца

Глобальные настройки имеют приоритет над тарифом:

- active tariff;
- enabled providers;
- default strategy;
- emergency strategy override;
- paid provider policy: `inherit / deny / allow_with_budget`;
- paid fan-out policy: `inherit / deny / allow_with_budget`;
- hard mission cost ceilings RUB/USD.

Тариф не может включить provider, запрещённый глобально, или превысить hard cost ceiling.

## Cost guard

Платный provider разрешается только если одновременно выполнены необходимые условия:

1. provider включён глобально;
2. тариф и глобальная policy не запрещают paid usage;
3. для fan-out отдельно разрешён paid fan-out;
4. стоимость provider известна (`cost_amount > 0`);
5. существует ненулевой currency budget;
6. не превышена global quota;
7. circuit breaker не открыт.

Ни один тарифный preset сам по себе не является разрешением расходовать деньги.

## Cache correctness

Search cache key включает не только query fingerprint, но и identity стратегии/provider-policy. Поэтому результат `primary_only` или fallback не может ошибочно использоваться как cached result для union режима.

## Billing integration contract

Будущий billing не должен копировать Search Gateway policy. Account/subscription слой хранит только выбранный tariff/profile ID. Effective search policy формируется в одном месте:

`global owner policy → selected tariff search profile → base environment safety policy → Search Gateway`.

## Диагностика

FULL/forensic trace фиксирует для Hunter:

`Query Intelligence → strategy/provider order → provider waterfall → result items → dedupe/exclude → pre-score → deep audit → final output`.

Это позволяет сравнивать стратегии по фактическим метрикам recall, unique yield, latency и cost, а не по предположениям.
