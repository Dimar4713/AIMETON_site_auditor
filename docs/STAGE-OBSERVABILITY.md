# AIMETON stage observability baseline

## Назначение

Лёгкий read-only контур наблюдаемости для текущего stage-узла AIMETON. Он не требует Prometheus, Grafana или отдельной базы метрик и рассчитан на VM с 2 vCPU и 4 GiB RAM.

## Наблюдаемые сигналы

- CPU count и load average;
- использование RAM и swap;
- использование диска и inode;
- состояния, health и restart count Docker-контейнеров;
- внешний `/api/health`;
- MCP redirect и MCP initialize;
- работа self-hosted runner services;
- статус канонической OpenStack VM;
- длительность самого collector.

Контур не собирает process environments, secrets, внутренние IP-адреса, содержимое пользовательских запросов и журналы приложения.

## Пороговые значения

Значения управляются через variables environment `stage`:

| Variable | Default | Назначение |
|---|---:|---|
| `OBS_DISK_WARNING` | 70 | warning по диску и inode |
| `OBS_DISK_CRITICAL` | 85 | critical по диску и inode |
| `OBS_MEMORY_WARNING` | 85 | warning по RAM |
| `OBS_SWAP_WARNING` | 50 | warning по swap |
| `OBS_LATENCY_WARNING_MS` | 3000 | warning по внешним пробам |

Critical также формируется при недоступности Docker, unhealthy/stopped container, неуспешном health/MCP или неактивной канонической OpenStack VM.

## Запуск

Workflow `Stage Observability` выполняется:

- каждые 6 часов;
- вручную через `workflow_dispatch`;
- по label `observability-check` на Issue #38.

Плановый запуск с состоянием `ok` не создаёт комментариев. Комментарий в #38 создаётся только при warning/critical либо при ручном/label-triggered запуске.

## Evidence и alerting

Каждый запуск сохраняет sanitized artifact `stage-observability-<run_id>` на 30 дней.

При critical workflow завершается красным статусом после загрузки evidence и публикации краткого alert в #38. Это отделяет сигнализацию от самого Site Auditor: приложение не отвечает за наблюдение за собой.

## SLI baseline

- `/api/health` доступен и отвечает HTTP 200;
- MCP initialize доступен и отвечает HTTP 200;
- каноническая OpenStack VM находится в `ACTIVE`;
- все обязательные контейнеры запущены, health не `unhealthy`;
- два self-hosted runner service присутствуют;
- disk/inode ниже critical threshold;
- collector выполняется менее 60 секунд и не поддерживает постоянный демон.

## Ограничения v0.1

Это контроль текущего состояния, а не долговременная time-series аналитика. Исторические данные сохраняются в Actions artifacts и событиях Issue. Переход к внешнему metrics stack оправдан после разделения management node и application node либо при появлении нескольких Execution Mesh nodes.
