# Политика ревизии и удаления архивных веток / Archived Branch Retention Policy

## RU

Архивирование и удаление являются двумя разными операциями.

1. Ветка переводится в пространство имён `archiv_*`.
2. При первом обнаружении в архиве workflow записывает `first_seen_archived_at` в долговременный ledger.
3. Не реже одного раза в неделю выполняется автоматический `review` без удаления.
4. Кандидатом становится только ветка, пробывшая в карантине не менее 30 дней.
5. Из пакета исключаются default branch, heads открытых PR и защищённые шаблоны.
6. Для commit, недостижимого из `main`, перед удалением создаётся и проверяется аннотированный tag `archive-snapshot/...`.
7. Review формирует детерминированный manifest и SHA-256 digest.
8. Apply требует точную строку `DELETE ARCHIVED BRANCHES <digest>` и защищённый GitHub Environment `branch-governance`.
9. Перед удалением повторно проверяется exact branch SHA; после удаления выполняется read-back отсутствия ref.
10. Manifest, ledger и result сохраняются как evidence artifact на 90 дней и публикуются в управляющую Issue.

Плановый запуск никогда не удаляет ветки. Он только обновляет ledger и публикует ревизию. Фактическое удаление выполняется отдельным ручным запуском подтверждённого пакета.

## EN

Archiving and deletion are separate operations.

1. A branch is moved into the `archiv_*` namespace.
2. On first archived discovery, the workflow records `first_seen_archived_at` in a durable ledger.
3. An automatic non-mutating review runs at least weekly.
4. A branch becomes eligible only after a minimum 30-day quarantine.
5. The default branch, open PR heads, and protected patterns are excluded.
6. A commit not reachable from `main` receives a verified annotated `archive-snapshot/...` tag before deletion.
7. Review produces a deterministic manifest and SHA-256 digest.
8. Apply requires the exact `DELETE ARCHIVED BRANCHES <digest>` confirmation and the protected `branch-governance` GitHub Environment.
9. Exact branch SHA is checked immediately before deletion and ref absence is read back afterward.
10. Manifest, ledger, and result are retained as evidence artifacts for 90 days and reported to the governance Issue.

Scheduled runs never delete branches. They only update the ledger and publish a review. Deletion is a separate manually approved execution of an exact reviewed package.
