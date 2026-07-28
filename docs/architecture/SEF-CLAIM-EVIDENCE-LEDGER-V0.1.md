# AIMETON SEF — Claim & Evidence Ledger v0.1

## Назначение

Ledger превращает набор claims и evidence в проверяемое состояние перед
Company Profile v1. Он не изменяет исходный `SefBundle`: история claims,
evidence и review decisions остаётся append-oriented.

## Вход и выход

```text
SefBundle + EvidenceMetadata + LedgerPolicy + as_of
→ LedgerSnapshot
  → evidence freshness/tier
  → conflict groups
  → effective review state
  → client eligibility
  → coverage summary
```

Канонические артефакты:

- модели и вычисление: `app/sef/ledger.py`;
- JSON Schema: `schemas/sef-ledger-v0.1.schema.json`;
- генератор схемы: `scripts/export_sef_ledger_schema.py`;
- SQL-расширение: `migrations/sef/0002_claim_evidence_ledger_v0_1.sql`;
- проверки: `tests/test_claim_evidence_ledger.py`.

## Evidence tiers

| Tier | Назначение |
|---|---|
| `tier_1_authority` | официальный реестр или равнозначный авторитетный источник |
| `tier_2_first_party` | первичный документ самой компании |
| `tier_3_independent` | допустимый независимый источник |
| `tier_4_signal` | слабый сигнал, недостаточный по умолчанию |
| `unassessed` | tier ещё не назначен; использование fail-closed |

Tier не заменяет freshness. Допустимость evidence определяется одновременно
политикой predicate, tier и состоянием свежести на момент `as_of`.

## Инварианты

1. Claims с разными значениями одного `entity + predicate` сохраняются и
   объединяются в детерминированную conflict group.
2. Конфликт считается разрешённым, только когда один claim одобрен, а все
   остальные отклонены последними решениями человека.
3. Последнее решение определяется парой `decided_at + decision_id`; более
   ранние решения не удаляются. Решение из будущего относительно `as_of` или
   принятое до claim/evidence не действует.
4. `rejected`, `needs_more_evidence` и отсутствие `approved` для критического
   claim блокируют client-facing использование.
5. Устаревшее evidence допускается только после явного `approved`; отсутствие
   metadata или неподходящий tier остаются fail-closed. Одобрение устаревшего
   evidence должно быть принято после окончания его freshness window.
6. Неразрешённый конфликт блокирует все входящие claims.
7. Summary показывает critical coverage, stale evidence, unresolved conflicts
   и pending review.
8. Потребитель обязан вызвать `require_client_eligible_claims` перед
   формированием client-facing секции; неизвестный или заблокированный claim
   отклоняется fail-closed с machine-readable reason codes.

## Граница ответственности

Ledger не формирует профиль компании и не разрешает противоречия с помощью
LLM. `SA-SEF-05` получает только ledger snapshot и использует
`client_eligible=true` для клиентских секций.
