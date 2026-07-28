# Документация AIMETON Site Auditor

## Исследовательские основания

- [Исследовательские основания развития всей поисково-разведывательной системы](research/AIMETON_Site_Auditor_full_system_search_research.md) — история рассуждений и причин архитектурных решений: выводы тестирования KIMI, переход от расширенного поиска к 12 РПТК, фрактальности, многоплоскостности, свойствам мишеней, сценариям, федеративным провайдерам, Evidence/Entity Graph и адаптивному усушению ветвей.
- [Evidence Memory и первый RAG-контур](research/AIMETON_Evidence_Memory_OpenRAG_research.md) — отдельное исследование подсистемы памяти, причины выбора архитектуры и путь от Document RAG к операционной онтологии AIMETON.

## Главный план развития

- [Полный план развития системы поиска, анализа и действий](roadmap/AIMETON_Site_Auditor_full_system_development_plan.md) — целевая архитектура Site Auditor как прикладного Runtime AIMETON: 12 РПТК, федеративный поиск, многоплоскостность, фрактальные ветви, усушение поиска, свойства мишеней, сценарии, Evidence/Entity Graph, Hunter, отчётность, Capability Management и очередность реализации.
- [SEF T0 baseline](baseline/SEF-T0-BASELINE-2026-07-28.md) — точные SHA сервиса, stage, Sentinel и инфраструктуры, evidence ATS-09A, teardown/no-orphan и честная фиксация красного внешнего валидатора.
- [SEF Benchmark-20 v0.1](benchmarks/SEF-BENCHMARK-20-V0.1.md) — замороженная выборка из 20 компаний и ручной identity-эталон для первых пяти.
- [SEF Mission и Evidence Contract v0.1](architecture/SEF-CONTRACT-V0.1.md) — provider-neutral модель данных, SQL-миграция и fail-closed инварианты доказательности.
- [SEF Provider Gateway v0.1](architecture/SEF-PROVIDER-GATEWAY-V0.1.md) — единый контракт Yandex/SearXNG/Tavily, cache, fallback, бюджет, circuit breaker и безопасная телеметрия.
- [SEF Document Fetch/Extract v0.1](architecture/SEF-DOCUMENT-FETCH-EXTRACT-V0.1.md) — HTTP-first загрузка, Crawl4AI/browser fallback, digest, locators и строгий переход `hint → document → evidence`.

## Политики управления

- [Политика и правила управления проектом](governance/AIMETON_Project_Management_Policy.md) — GitHub Projects как оперативный центр, источники истины, иерархия Initiative → Epic → Issue → Sub-issue, обязательные поля и представления, шаблоны Issue/PR, Definition of Ready/Done и трассировка Alpha → Omega.

## Архитектура памяти и RAG

- [Детальный план реализации Evidence Memory](roadmap/AIMETON_Site_Auditor_Evidence_Memory_implementation_plan.md) — подсистемный трек главного плана: этапы M0–M10, простые действия, критерии приёмки, контрольные точки и первый спринт EM-01.

## Очерёдность старта

1. Создать GitHub Project `AIMETON Development Control` по принятой политике.
2. `SA-01` — стабилизация текущего поискового и MCP-контура.
3. Evidence и Entity contracts.
4. Федеративный SearchProvider layer.
5. `EM-01` — сохранение оригиналов и provenance за feature flag.
6. Новый отчёт и дальнейшее развёртывание Раструба.

## Принцип реализации

```text
малое изменение
→ тест
→ наблюдаемый результат
→ фиксация опыта
→ следующий простой шаг
```

Индексы RAG не являются источником истины: оригиналы и provenance должны позволять полностью перестроить поисковый слой.
