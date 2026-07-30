# Identity Benchmark-5 v0.1

Статус: слит PR `#105`, развёрнут на stage как `0.16.2 /
45b38b81079bd13a1690bf84283ebeb7b101087f`. PR Baseline CI
`#30540392356`, main Baseline CI `#30540507493` и Deploy Stage
`#30540595302` — success.

## Назначение

`IDENTITY-BENCHMARK-5` проверяет детерминированный путь:

```text
sanitized first-party HTML
  → bootstrap identity extraction
  → provenance-bearing signals
  → provisional Entity Resolution
  → exact Golden-5 legal name + INN + OGRN
```

Эталоном является `benchmarks/sef/golden-5-v0.1.json`. Тест не обращается к
сети, search provider или LLM и не обновляет golden по фактическому ответу.

## Состав

Используются первые пять замороженных случаев `SEF-BENCHMARK-20`:

- Первая Климатическая Компания;
- Sib Dental Clinic;
- CDEK;
- Timeweb;
- REG.RU.

Fixture минимизированы и сохраняют разные структуры первичных страниц:
`dl/dt/dd`, label/value, таблицу, полную правовую форму, банковского
контрагента и длинное юридическое имя. Они не являются новой копией
юридического эталона: ожидаемые значения читаются только из Golden-5.

## Инварианты

- выбран ровно один provisional target;
- normalized legal name, ИНН и ОГРН точно совпадают с Golden-5;
- competing candidate не подменяет target;
- конфликт отсутствует только при однозначном наборе сильных идентификаторов;
- bootstrap не создаёт `accepted_identifier_links`;
- отдельный отрицательный тест Entity Resolution сохраняет различие
  `ООО «Дедал»` и `ООО «Дедал Плюс»`.

## Запуск

```bash
pytest -q tests/test_identity_benchmark5.py
pytest -q
```
