# Stage retention policy

## Назначение

Политика ограничивает рост локальных deployment bundles на stage-сервере, не смешивая deployment, rollback и destructive cleanup в одну операцию.

## Базовые правила

- deployment никогда не удаляет старые bundles автоматически;
- retention запускается отдельным workflow;
- режим `plan` является read-only;
- режим `apply` требует точную строку подтверждения из последнего plan;
- текущий `app-source` не является кандидатом очистки;
- три newest `app-source.backup.*` защищены по умолчанию;
- два newest `app-source.failed.*`/`app-source.manual-failed.*` защищены по умолчанию;
- любой bundle с файлом `.retention-protected` защищён независимо от возраста;
- symbolic links и пути вне `.deployments` игнорируются и не удаляются;
- OpenStack snapshots/images этим контуром не удаляются.

## Пороги диска

- normal: менее 70%;
- warning: 70–84.9%;
- critical: 85% и выше.

Порог сам по себе не запускает destructive cleanup. Он только фиксируется в evidence и используется для принятия решения.

## Dry-run

Автоматический read-only plan запускается меткой `retention-plan` на Issue #37 или вручную:

`Actions → Stage Retention → Run workflow → mode=plan`.

Plan публикует:

- процент использования диска;
- защищённые bundles;
- кандидатов очистки;
- потенциально освобождаемое место;
- точную confirmation-строку формата `CLEANUP <count> <digest>`.

## Controlled apply

Apply запускается только вручную через `workflow_dispatch` с теми же значениями `keep_backups` и `keep_failed`, что использовались в plan, и с точной confirmation-строкой.

Перед и после операции workflow проверяет:

- `/api/health`;
- `/mcp → 307`.

При несовпадении списка кандидатов digest меняется, поэтому устаревшее подтверждение не принимается.

## GitHub artifacts

Рекомендуемая политика:

- deployment evidence: 30 дней;
- retention evidence: 30 дней;
- snapshot/recovery evidence: 90 дней;
- архитектурные решения и итоговые сводки должны переноситься в Issues/Docs и не зависеть только от artifacts.

## OpenStack images

Удаление snapshot/image остаётся отдельной инфраструктурной операцией с собственным планом, подтверждением UUID и evidence. Автоматическое удаление OpenStack images запрещено.
