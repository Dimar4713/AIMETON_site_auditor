# Krasnoyarsk dentistry Search Gateway snapshot/replay benchmark

Providers: yandex, tavily, searxng
Reference union: 75 probable direct-company domains; regional subset: 64.

| Rank | Strategy | Score | Direct | Precision | Recall | Regional recall | Corroboration | Simulated seconds | Calls | Cost RUB | Cost USD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | `consensus_union` | 76.38 | 71 | 68.9% | 94.7% | 92.2% | 38.0% | 17.52 | yandex:8/tavily:8/searxng:8 | 0.08 | 0.064 |
| 2 | `exhaustive_coverage` | 75.36 | 75 | 66.4% | 100.0% | 96.9% | 21.3% | 31.70 | yandex:8/tavily:8/searxng:8 | 0.08 | 0.064 |
| 3 | `adaptive_cost_quality` | 75.25 | 67 | 78.8% | 89.3% | 90.6% | 28.4% | 29.67 | yandex:8/tavily:8/searxng:5 | 0.08 | 0.064 |
| 4 | `parallel_union` | 74.99 | 67 | 77.9% | 89.3% | 87.5% | 19.4% | 17.52 | yandex:8/tavily:8/searxng:8 | 0.08 | 0.064 |
| 5 | `cascade_until_target` | 74.10 | 67 | 77.9% | 89.3% | 87.5% | 19.4% | 28.83 | yandex:8/tavily:8/searxng:4 | 0.08 | 0.064 |
| 6 | `sequential_union` | 73.87 | 67 | 77.9% | 89.3% | 87.5% | 19.4% | 31.69 | yandex:8/tavily:8/searxng:8 | 0.08 | 0.064 |
| 7 | `fallback_first_nonempty` | 64.78 | 47 | 87.0% | 62.7% | 65.6% | 0.0% | 9.72 | yandex:8/tavily:0/searxng:0 | 0.08 | 0 |
| 8 | `primary_only` | 64.78 | 47 | 87.0% | 62.7% | 65.6% | 0.0% | 9.72 | yandex:8/tavily:0/searxng:0 | 0.08 | 0 |
| 9 | `shadow_compare` | 62.20 | 47 | 87.0% | 62.7% | 65.6% | 0.0% | 26.52 | yandex:8/tavily:8/searxng:8 | 0.08 | 0.064 |
| 10 | `split_query_routing` | 56.20 | 37 | 71.2% | 49.3% | 54.7% | 35.1% | 11.97 | yandex:3/tavily:3/searxng:2 | 0.03 | 0.024 |

## Top probable direct-company domains

### 1. `consensus_union`
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=6 — searxng,yandex
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=6 — tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=6 — tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=5 — tavily,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=5 — tavily,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=4 — tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=4 — tavily,yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `dostupstom24.ru` — Доступная стоматология в Красноярске | Лечение зубов без боли — q=3 — tavily,yandex
- `stomferos.ru` — Стоматология в Красноярске - клиника «Ферос» (Октябрьский...) — q=3 — tavily,yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex

### 2. `exhaustive_coverage`
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=7 — searxng,tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=7 — searxng,tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=6 — searxng,tavily,yandex
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=6 — tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=5 — tavily,yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске - записаться на прием — q=5 — searxng,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=5 — tavily,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=4 — tavily,yandex
- `voka-stom.ru` — Стоматология ВОКА в Красноярске - стоматологическая... — q=4 — searxng,yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `crystal-dent.ru` — Стоматология в Красноярске | CRYSTAL-DENT — q=3 — searxng,yandex

### 3. `adaptive_cost_quality`
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=6 — tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=6 — tavily,yandex
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — searxng,tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=5 — searxng,tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=5 — searxng,tavily,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=5 — tavily,yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске - записаться на прием — q=4 — searxng,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=4 — tavily,yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — searxng,yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `dostupstom24.ru` — Доступная стоматология в Красноярске | Лечение зубов без боли — q=3 — tavily,yandex
- `stomferos.ru` — Стоматология в Красноярске - клиника «Ферос» (Октябрьский...) — q=3 — tavily,yandex

### 4. `parallel_union`
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=6 — tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=6 — tavily,yandex
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — searxng,tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=5 — tavily,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=5 — tavily,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=4 — tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=4 — tavily,yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `dostupstom24.ru` — Доступная стоматология в Красноярске | Лечение зубов без боли — q=3 — tavily,yandex
- `stomferos.ru` — Стоматология в Красноярске - клиника «Ферос» (Октябрьский...) — q=3 — tavily,yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex

### 5. `cascade_until_target`
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=6 — tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=6 — tavily,yandex
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — searxng,tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=5 — tavily,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=5 — tavily,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=4 — tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=4 — tavily,yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `dostupstom24.ru` — Доступная стоматология в Красноярске | Лечение зубов без боли — q=3 — tavily,yandex
- `stomferos.ru` — Стоматология в Красноярске - клиника «Ферос» (Октябрьский...) — q=3 — tavily,yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex

### 6. `sequential_union`
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=6 — tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=6 — tavily,yandex
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — searxng,tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=5 — tavily,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=5 — tavily,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=4 — tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=4 — tavily,yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `dostupstom24.ru` — Доступная стоматология в Красноярске | Лечение зубов без боли — q=3 — tavily,yandex
- `stomferos.ru` — Стоматология в Красноярске - клиника «Ферос» (Октябрьский...) — q=3 — tavily,yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex

### 7. `fallback_first_nonempty`
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — yandex
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=5 — yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=5 — yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=4 — yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=4 — yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex
- `klass-dent.ru` — Стоматология класса комфорт по доступным ценам в Красноярске — q=3 — yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=3 — yandex
- `sapfircs.ru` — Стоматология в Красноярске — Центр стоматологии Сапфир — q=3 — yandex
- `sibdentalclinic.ru` — Стоматология в Красноярске — лечение зубов в клинике... — q=3 — yandex

### 8. `primary_only`
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — yandex
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=5 — yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=5 — yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=4 — yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=4 — yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex
- `klass-dent.ru` — Стоматология класса комфорт по доступным ценам в Красноярске — q=3 — yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=3 — yandex
- `sapfircs.ru` — Стоматология в Красноярске — Центр стоматологии Сапфир — q=3 — yandex
- `sibdentalclinic.ru` — Стоматология в Красноярске — лечение зубов в клинике... — q=3 — yandex

### 9. `shadow_compare`
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — yandex
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=5 — yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=5 — yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=4 — yandex
- `dentist-stom.ru` — Стоматология Dentist: эстетическое лечение зубов в Красноярске... — q=4 — yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=4 — yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=4 — yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске... — q=3 — yandex
- `klass-dent.ru` — Стоматология класса комфорт по доступным ценам в Красноярске — q=3 — yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=3 — yandex
- `sapfircs.ru` — Стоматология в Красноярске — Центр стоматологии Сапфир — q=3 — yandex
- `sibdentalclinic.ru` — Стоматология в Красноярске — лечение зубов в клинике... — q=3 — yandex

### 10. `split_query_routing`
- `aldenta.ru` — Частная стоматология в Красноярске Al'denta (Альдента) — q=5 — searxng,tavily,yandex
- `nita-stom.ru` — Стоматология для взрослых и детей в Красноярске: записаться... — q=5 — searxng,tavily,yandex
- `apex24.ru` — Стоматология Апекс в Красноярске — q=4 — searxng,tavily,yandex
- `zyboff.ru` — Стоматологическая клиника ЗУБОFF | Стоматология Красноярск — q=4 — searxng,tavily,yandex
- `crystal-dent.ru` — Стоматология в Красноярске | CRYSTAL-DENT — q=3 — searxng,tavily,yandex
- `klinikaps.ru` — Стоматология ЖД района Красноярска - Клиника практической... — q=3 — yandex
- `astreyastom.ru` — Стоматология АСТРЕЯ - лечение зубов в Красноярске - записаться на прием — q=2 — searxng,yandex
- `medident.ru` — Стоматология в Красноярске — МедиДент — q=2 — searxng,yandex
- `mira-stom.ru` — Стоматология в Красноярске Mira — Лечение зубов — q=2 — tavily,yandex
- `profnik.ru` — Имплантация зубов в Красноярске | цены в клинике Николаенко... — q=2 — tavily,yandex
- `sapfircs.ru` — Стоматология в Красноярске — Центр стоматологии Сапфир — q=2 — searxng,yandex
- `sibstom24.info` — Сибстом - семейная стоматология в Красноярске — q=2 — tavily,yandex
