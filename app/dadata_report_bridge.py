from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from app.entity_resolution.dadata import (
    DaDataLookupResult,
    RegistryMirrorState,
    get_dadata_registry_mirror_provider,
)
from app.models import CompanyFact


DADATA_NOTE_PREFIX = "DaData registry mirror"


async def enrich_identity_with_dadata(
    anchors: Any,
) -> tuple[Any, DaDataLookupResult | None, list[CompanyFact], list[str]]:
    """Resolve extracted INN/OGRN against DaData without upgrading authority trust.

    DaData is deliberately treated as a registry mirror. It can corroborate and
    normalize entity identity, but it can never close the FNS authority gate.
    The synchronous provider is moved off the async mission worker thread.
    """
    query = getattr(anchors, "inn", None) or getattr(anchors, "ogrn", None)
    if not query:
        return anchors, None, [], [
            f"{DADATA_NOTE_PREFIX}: not_attempted — INN/OGRN не извлечён из first-party evidence."
        ]

    provider = get_dadata_registry_mirror_provider()
    try:
        result = await asyncio.to_thread(provider.lookup, str(query))
    except RuntimeError:
        return anchors, None, [], [
            f"{DADATA_NOTE_PREFIX}: unavailable — provider lookup failed; authority gate ФНС остаётся открытым."
        ]

    notes = [
        f"{DADATA_NOTE_PREFIX}: state={result.state.value}; records={len(result.records)}; "
        f"cache_hit={str(result.cache_hit).lower()}; authority_verified=false."
    ]
    facts: list[CompanyFact] = []
    for record in result.records[:10]:
        fact_note = (
            f"{DADATA_NOTE_PREFIX}; state={result.state.value}; "
            f"authority_verified=false; response_digest={record.response_digest}"
        )
        for field, value in (
            ("legal_name", record.legal_name),
            ("inn", record.inn),
            ("ogrn", record.ogrn),
            ("registration_status", record.status),
        ):
            if value:
                facts.append(
                    CompanyFact(
                        field=field,
                        value=str(value),
                        confidence="Средняя",
                        source_ids=[],
                        note=fact_note,
                    )
                )

    if result.state is RegistryMirrorState.VERIFIED and len(result.records) == 1:
        record = result.records[0]
        anchors = replace(
            anchors,
            legal_name=record.legal_name or getattr(anchors, "legal_name", None),
            inn=record.inn or getattr(anchors, "inn", None),
            ogrn=record.ogrn or getattr(anchors, "ogrn", None),
        )
        notes.append(
            f"{DADATA_NOTE_PREFIX}: идентификаторы нормализованы для дальнейшего discovery; "
            "официальная верификация ФНС всё ещё обязательна."
        )
    elif result.state is RegistryMirrorState.CONFLICTING:
        notes.append(
            f"{DADATA_NOTE_PREFIX}: получены конфликтующие/множественные записи; "
            "identity не повышена до resolved без authority evidence ФНС."
        )
    elif result.state is RegistryMirrorState.UNRESOLVED:
        notes.append(
            f"{DADATA_NOTE_PREFIX}: запись по извлечённому идентификатору не разрешена; "
            "исходные first-party anchors сохранены."
        )

    return anchors, result, facts, notes
