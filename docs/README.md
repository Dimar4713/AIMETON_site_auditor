# Документация AIMETON Site Auditor

## Главный план развития

- [Полный план развития системы поиска, анализа и действий](roadmap/AIMETON_Site_Auditor_full_system_development_plan.md) — целевая архитектура Site Auditor как прикладного Runtime AIMETON: 12 РПТК, федеративный поиск, многоплоскостность, фрактальные ветви, усушение поиска, свойства мишеней, сценарии, Evidence/Entity Graph, Hunter, отчётность, Capability Management и очередность реализации.

## Архитектура памяти и RAG

- [Evidence Memory и первый RAG-контур](research/AIMETON_Evidence_Memory_OpenRAG_research.md) — исследовательская записка, причины выбора архитектуры и путь от Document RAG к операционной онтологии AIMETON.
- [Детальный план реализации Evidence Memory](roadmap/AIMETON_Site_Auditor_Evidence_Memory_implementation_plan.md) — подсистемный трек главного плана: этапы M0–M10, простые действия, критерии приёмки, контрольные точки и первый спринт EM-01.

## Очерёдность старта

1. `SA-01` — стабилизация текущего поискового и MCP-контура.
2. Evidence и Entity contracts.
3. Федеративный SearchProvider layer.
4. `EM-01` — сохранение оригиналов и provenance за feature flag.
5. Новый отчёт и дальнейшее развёртывание Раструба.

## Принцип реализации

```text
малое изменение
→ тест
→ наблюдаемый результат
→ фиксация опыта
→ следующий простой шаг
```

Индексы RAG не являются источником истины: оригиналы и provenance должны позволять полностью перестроить поисковый слой.