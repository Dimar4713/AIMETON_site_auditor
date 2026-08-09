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
| `parallel_union` | параллельный fan-out и merge | высокий, меньшая latency | средняя/высокая | implemented |
| `consensus_union` | union + приоритет доменов, найденных несколькими providers | высокий + corroboration | высокая | implemented |
| `split_query_routing` | разные LLM query variants распределяются между providers | высокий при меньшем fan-out | управляемая | implemented |
| `adaptive_cost_quality` | динамический порядок по yield/latency/health и cost-priority | адаптивный | оптимизируемая | implemented |
| `exhaustive_coverage` | все allowed providers × query в пределах hard caps | максимальный | максимальная | implemented |
| `shadow_compare` | secondary providers работают для benchmark, не меняя выдачу | диагностический | дополнительная | implemented/internal |

`cache-first` является ортогональным поведением и не считается отдельной стратегией.

## Семантика режимов

### primary_only
Используется первый реально доступный и разрешённый provider. После первой фактической попытки другие providers не вызываются.

### fallback_first_nonempty
Классическая отказоустойчивость: providers вызываются по порядку; первый непустой результат становится ответом. Платный secondary вызов регулируется `allow_paid_fallback` и budget guard.

### cascade_until_target
Результаты providers последовательно объединяются и дедуплицируются. Каскад прекращается при достижении `target_results` либо `max_providers_per_query`.

### sequential_union
Все разрешённые providers вызываются последовательно до `max_providers_per_query`; результаты объединяются и дедуплицируются. Платный secondary fan-out требует отдельного разрешения.

### parallel_union
Разрешённые providers запускаются конкурентно. Это уменьшает wall-clock latency, но не уменьшает число provider calls. Платные вторичные вызовы по-прежнему проходят отдельный fan-out cost guard.

### consensus_union
Используется multi-provider union, после чего результаты агрегируются по домену. Домен, найденный несколькими независимыми providers, получает `corroborated_by` и располагается выше доменов с одним источником подтверждения. Это не является доказательством юридической идентичности компании; это только cross-provider discovery signal.

### split_query_routing
Каждый Query Intelligence variant детерминированно направляется одному готовому provider. Разные формулировки распределяются между движками без полного `queries × providers` fan-out. Маршрутизация учитывает configured/allowed, circuit, quota, известную цену и доступный mission budget.

### adaptive_cost_quality
Gateway ведёт runtime-наблюдения по providers: transport success, result yield и latency. Перед новым query providers переупорядочиваются по успешности, yield, latency и cost-priority, после чего выполняется bounded cascade до target. При отсутствии истории используется безопасный исходный порядок. Runtime observations не являются долговременным бизнес-рейтингом providers и сбрасываются с процессом.

### exhaustive_coverage
Все разрешённые providers вызываются до `max_providers_per_query` независимо от `target_results`. Максимальный размер объединённой выдачи ограничивается суммарным fan-out ceiling и общим hard limit Gateway. Budget/quota/circuit guards не отключаются.

### shadow_compare
Возвращается только результат primary provider. Secondary providers исполняются для benchmark/диагностики и не влияют на пользовательскую выдачу. Cache специально не используется, иначе benchmark не сравнивал бы реальные provider calls. Любой платный shadow-вызов считается secondary fan-out и требует отдельного разрешения. Режим предназначен только для global/debug и не доступен как тарифная стратегия.

## Наследование стратегии

Тариф может либо задать конкретную tariff-safe стратегию, либо выбрать **«Наследовать глобальную стратегию»**. Effective strategy формируется так:

`emergency strategy override → tariff strategy → global default strategy`.

`shadow_compare` доступен только на глобальном/debug уровне и не может быть сохранён в тарифном профиле.

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

Эти presets можно менять через админ-панель. Само имя `Free/Start/Pro/Max` не даёт разрешения на платные вызовы.

## Глобальная политика владельца

Глобальные настройки задают верхние границы:

- active tariff;
- enabled providers;
- global default strategy;
- emergency strategy override;
- paid provider policy: `inherit / deny / allow_with_budget`;
- paid fan-out policy: `inherit / deny / allow_with_budget`;
- hard mission cost ceilings RUB/USD.

Тариф не может включить provider, запрещённый глобально, или превысить hard cost ceiling.

## Cost guard

Платный provider разрешается только если одновременно выполнены необходимые условия:

1. provider включён глобально;
2. тариф и global policy не запрещают paid usage;
3. для secondary/fan-out отдельно разрешён paid fan-out;
4. стоимость provider известна (`cost_amount > 0`);
5. существует ненулевой currency budget;
6. не превышена global quota;
7. circuit breaker не открыт.

Ни один тарифный preset сам по себе не является разрешением расходовать деньги.

## Cache correctness

Search cache key включает query fingerprint и identity эффективной стратегии/provider-policy. Поэтому single-provider cache не может ошибочно удовлетворить union/consensus/exhaustive запрос. `shadow_compare` cache обходит полностью.

## Billing integration contract

Будущий billing не должен копировать Search Gateway policy. Account/subscription слой хранит только выбранный tariff/profile ID. Effective search policy формируется в одном месте:

`global owner policy → selected tariff search profile → runtime environment safety policy → Search Gateway`.

## Диагностика

FULL/forensic trace фиксирует для Hunter:

`Query Intelligence → effective strategy/provider order → provider waterfall → normalized result items/corroboration → dedupe/exclude → pre-score → deep audit → final output`.

Это позволяет сравнивать стратегии по фактическим метрикам recall, unique yield, latency и cost, а не по предположениям.

## Benchmark dimensions

Стратегии следует сравнивать минимум по:

- unique relevant-company recall;
- provider contribution/yield;
- cross-provider duplicate rate;
- supporting-source noise rate;
- latency;
- cost per retained useful candidate;
- fallback/degradation behavior;
- classification accuracy after Hunter qualification.

Контрольный сценарий `Красноярск / стоматология` является reference benchmark, но не должен становиться единственной оптимизационной выборкой.
