# Registry Runtime and Human Review v0.1

## Назначение

Срез связывает provisional Entity Resolution с authority gate официального реестра и append-only журналом решений человека.

## Исполнимый маршрут

`identity revision → RegistryEvidence → OfficialRegistryVerifier → verified/review/conflict → optional identity promotion`

Публичные маршруты размещены под `/api/missions`:

- `POST /{mission_id}/verify-registry`;
- `POST /{mission_id}/registry-reviews/{review_id}`;
- `GET /{mission_id}/registry-history`.

## Fail-closed правила

1. В verifier передаётся только уже полученный документ с URL, locator, digest и authority.
2. Автоматическая promotion разрешена только для `verified`, при наличии accepted identifier links и отсутствии conflict/human review.
3. Переданный promotion plan при непродвигаемом результате отклоняется.
4. Human review не может переопределить расхождение ИНН/ОГРН. Решение сохраняется отдельно и не превращает конфликт в verified.
5. Решение review append-only: повтор идентичного решения идемпотентен, изменение запрещено.
6. Branch, brand, owner и affiliate не считаются исследуемым субъектом автоматически.

## Граница среза

Runtime принимает нормализованный `RegistryEvidence`, но не выполняет сетевой запрос к ФНС. Для production connector требуется законный и устойчивый способ получения официальной выписки/записи, контракт аутентификации и политика хранения исходного документа.
