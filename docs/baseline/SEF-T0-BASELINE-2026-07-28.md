# SEF T0 baseline

**Дата фиксации:** 28 июля 2026

**Статус:** зафиксирован; повторный зелёный ATS-09A run остаётся контрольным действием

**Следующий этап:** `SA-SEF-01`

## Точные версии

| Объект | Идентификатор | Доказательство |
|---|---|---|
| Site Auditor `main` после принятия тактического плана | `7d2b5dd7cd6828e5331971cb20070663b503db05` | merge commit PR `AIMETON_site_auditor#62` |
| Код, фактически развёрнутый на stage во время ATS-09A | `cdcf9adfddce84a57c989a26002b21372ab76e95` | ATS-09A `deployment_identity` |
| Sentinel | `fb19274fc1ec156a24e33ee85519804da5a8c2f8` | ATS-09A result и manifest |
| Infrastructure campaign source | `c506167f671215dfde3afb53e22f9c52e8d093ac` | artifact manifest |
| Исправление валидатора пакета | `f8d53655b1e54f6ae21eeed180b3c9033fa29e06` | merge commit `aimeton-infrastructure#45` |
| Зелёный Baseline CI плана T0 | run `30362281654` | Baseline CI для head PR `#62` |

Сервисный `main` новее deployment SHA только на документационный merge тактического плана. Функциональный baseline stage остаётся привязан к `cdcf9ad…`.

## ATS-09A и lifecycle временного VPS

Кампания: [`30196898540`](https://github.com/Dimar4713/aimeton-infrastructure/actions/runs/30196898540)

Artifact: `ats09a-stage-campaign-30196898540`, ID `8630403856`

Artifact digest: `sha256:c214f0f862dc56e82d4574bda68719ee36607a1819729579f84eb8d088e571a0`

Результат внутри пакета:

```text
campaign_id: ats09a-gh-30196898540-1
status: passed
deployment_sha: cdcf9adfddce84a57c989a26002b21372ab76e95
sentinel_sha: fb19274fc1ec156a24e33ee85519804da5a8c2f8
evidence_digest: c648105a408562f13b5e87285fd340a2b609fb33956fe82a43296e021096cb94
evidence_archive_sha256: 3ca95b5068f69674810e777b3ded51d9ce04ad5b029755ec8e90b40b90866d63
cleanup_verified: true
teardown_mode: destroy
cleanup_errors: []
```

Успешно подтверждены:

- DNS и TLS;
- exact deployment SHA;
- Runtime health;
- public MCP initialize;
- public MCP tools/list;
- admin endpoint без токена → `401`;
- admin endpoint с неверным токеном → `401`;
- сбор и digest evidence;
- удаление временного сервера без ошибок cleanup.

## Нюанс статуса workflow

Внешний job `live-campaign` run `30196898540` имеет conclusion `failure`, хотя `result.json`, полный ATS-09A result и cleanup journal имеют `status: passed`. Причина — прежний валидатор workflow читал сокращённый controller summary как полный result и не создавал каталог до `tee`.

Это исправлено в `aimeton-infrastructure#45`:

- создаётся evidence-каталог;
- отдельно проверяются summary и полный result из `evidence.tar.gz`;
- сохраняется обязательная проверка cleanup/no-orphan.

Исторический run нельзя объявлять зелёным задним числом. Перед T1 требуется повторный live-run на исправленном валидаторе; он должен завершиться зелёным на уровне GitHub job и сохранить тот же fail-closed contract.

## Управленческое решение T0

- Реализацию Runtime Core v0.1 считать завершённой в границах PR `AIMETON_site_auditor#49`.
- SA-03 считать завершённым как этап стабилизации после фиксации ссылок на live evidence.
- ATS-09A не закрывать как полностью подтверждённый до зелёного повторного run на исправленном валидаторе.
- Недостающие расширенные сценарии отказов не добавлять в ATS-09A задним числом; вести их в ATS-09C.
- Следующую разработку начинать с `SA-SEF-01`, сохраняя Runtime Core на SQLite до отдельного PostgreSQL store contract.
