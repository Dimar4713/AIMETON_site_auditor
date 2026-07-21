# Документация AIMETON Site Auditor

## Исследовательские основания

- [Исследовательские основания развития всей поисково-разведывательной системы](research/AIMETON_Site_Auditor_full_system_search_research.md) — история рассуждений и причин архитектурных решений: выводы тестирования KIMI, переход от расширенного поиска к 12 РПТК, фрактальности, многоплоскостности, свойствам мишеней, сценариям, федеративным провайдерам, Evidence/Entity Graph и адаптивному усушению ветвей.
- [Evidence Memory и первый RAG-контур](research/AIMETON_Evidence_Memory_OpenRAG_research.md) — отдельное исследование подсистемы памяти, причины выбора архитектуры и путь от Document RAG к операционной онтологии AIMETON.

## Главный план развития

- [Полный план развития системы поиска, анализа и действий](roadmap/AIMETON_Site_Auditor_full_system_development_plan.md) — целевая архитектура Site Auditor как прикладного Runtime AIMETON: 12 РПТК, федеративный поиск, многоплоскостность, фрактальные ветви, усушение поиска, свойства мишеней, сценарии, Evidence/Entity Graph, Hunter, отчётность, Capability Management и очередность реализации.

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