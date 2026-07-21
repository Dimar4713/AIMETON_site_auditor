# Документация AIMETON Site Auditor

## Архитектура памяти и RAG

- [Evidence Memory и первый RAG-контур](research/AIMETON_Evidence_Memory_OpenRAG_research.md) — исследовательская записка, причины выбора архитектуры и путь от Document RAG к операционной онтологии AIMETON.
- [Детальный план реализации Evidence Memory](roadmap/AIMETON_Site_Auditor_Evidence_Memory_implementation_plan.md) — этапы M0–M10, простые действия, критерии приёмки, контрольные точки и первый спринт EM-01.

## Принцип реализации

```text
малое изменение
→ тест
→ наблюдаемый результат
→ фиксация опыта
→ следующий простой шаг
```

Индексы RAG не являются источником истины: оригиналы и provenance должны позволять полностью перестроить поисковый слой.