# Stage retention policy

## Назначение

Политика ограничивает рост локальных deployment bundles на stage-сервере и сохраняет необходимое число точек rollback.

## Базовые правила

- после успешных health/MCP postflight deployment автоматически удаляет только bundles сверх заданного количества;
- количество сохраняемых bundles управляется вручную через stage variables;
- `STAGE_BACKUP_KEEP` задаёт число сохраняемых `app-source.backup.*`, значение по умолчанию — 5;
- `STAGE_FAILED_KEEP` задаёт число сохраняемых failed bundles каждого типа, значение по умолчанию — 2;
- текущий `app-source` никогда не является кандидатом очистки;
- любой bundle с файлом `.retention-protected` сохраняется независимо от порядкового номера;
- symbolic links и пути вне `.deployments` не удаляются;
- автоматическая очистка выполняется только после успешного deployment и smoke-проверок;
- OpenStack snapshots/images этим контуром не удаляются.

Таким образом, автоматизируется соблюдение численного лимита, а решение о самом лимите остаётся ручным.

## Пороги диска

- normal: менее 70%;
- warning: 70–84.9%;
- critical: 85% и выше.

Дисковые пороги фиксируются в evidence отдельного retention workflow. Они не меняют вручную заданное число сохраняемых bundles.

## Dry-run

Read-only plan запускается меткой `retention-plan` на Issue #37 или вручную:

`Actions → Stage Retention → Run workflow → mode=plan`.

Plan публикует:

- процент использования диска;
- защищённые bundles;
- кандидатов очистки при выбранных значениях keep;
- потенциально освобождаемое место;
- точную confirmation-строку формата `CLEANUP <count> <digest>`.

## Controlled apply

Отдельный ручной `apply` сохраняется для внеплановой очистки без нового deployment. Он требует те же значения `keep_backups` и `keep_failed`, что использовались в plan, и точную confirmation-строку.

Перед и после операции workflow проверяет:

- `/api/health`;
- `/mcp → 307`.

При несовпадении списка кандидатов digest меняется, поэтому устаревшее подтверждение не принимается.

## Изменение числа сохраняемых bundles

В GitHub:

`Settings → Environments → stage → Environment variables`

Переменные:

- `STAGE_BACKUP_KEEP`, например `5`;
- `STAGE_FAILED_KEEP`, например `2`.

Новые значения применяются при следующем успешном deployment. Значения должны быть неотрицательными целыми числами.

## GitHub artifacts

Рекомендуемая политика:

- deployment evidence: 30 дней;
- retention evidence: 30 дней;
- snapshot/recovery evidence: 90 дней;
- архитектурные решения и итоговые сводки должны переноситься в Issues/Docs и не зависеть только от artifacts.

## OpenStack images

Удаление snapshot/image остаётся отдельной инфраструктурной операцией с собственным планом, подтверждением UUID и evidence. Автоматическое удаление OpenStack images запрещено.
