from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Annotated, Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from app.models import CompanyFact, EconomicSignal


FactField = Literal[
    "legal_name", "brand_name", "inn", "ogrn", "registration_status",
    "address", "phones", "emails", "website", "social_accounts",
    "headcount", "revenue", "profit", "assets", "taxes",
    "founders", "executives", "beneficial_owners", "affiliates",
    "geography", "products", "customers", "suppliers", "other",
]
Confidence = Literal["Высокая", "Средняя", "Низкая"]
ShortText = Annotated[str, Field(max_length=240)]


class CompactCompanyFact(BaseModel):
    field: FactField
    value: str = Field(max_length=240)
    period: str | None = Field(default=None, max_length=64)
    confidence: Confidence = "Средняя"
    source_ids: list[str] = Field(default_factory=list, max_length=4)


class CompactEconomicSignal(BaseModel):
    signal: str = Field(max_length=140)
    evidence: str = Field(max_length=180)
    business_effect: str = Field(max_length=180)
    confidence: Confidence = "Средняя"
    source_ids: list[str] = Field(default_factory=list, max_length=4)


class IdentityProfileSlice(BaseModel):
    company_name: str = Field(max_length=160)
    business_summary: str = Field(max_length=480)
    evidence: list[ShortText] = Field(default_factory=list, max_length=5)
    company_facts: list[CompactCompanyFact] = Field(default_factory=list, max_length=12)
    risks_and_assumptions: list[ShortText] = Field(default_factory=list, max_length=4)


class OperationsProfileSlice(BaseModel):
    company_facts: list[CompactCompanyFact] = Field(default_factory=list, max_length=12)
    risks_and_assumptions: list[ShortText] = Field(default_factory=list, max_length=4)


class SignalProfileSlice(BaseModel):
    economic_signals: list[CompactEconomicSignal] = Field(default_factory=list, max_length=6)
    risks_and_assumptions: list[ShortText] = Field(default_factory=list, max_length=5)


@dataclass(frozen=True)
class MergedProfileExtraction:
    company_name: str
    business_summary: str
    evidence: list[str]
    company_facts: list[CompanyFact]
    economic_signals: list[EconomicSignal]
    risks_and_assumptions: list[str]


RequestJson = Callable[..., Awaitable[BaseModel]]

_IDENTITY_KINDS = {
    "official", "contact", "registry", "ownership", "affiliation", "social",
}
_OPERATIONS_KINDS = {
    "finance", "workforce", "jobs", "tender", "patent", "other",
}
_SIGNAL_KINDS = {
    "arbitration", "court", "enforcement", "news", "review", "social",
    "tender", "finance", "other",
}
_SLICE_SOURCE_KEYS = (
    "id", "title", "query_kind", "result_kind", "source_class",
    "evidence_level", "snippet",
)


def _source_slice(
    sources: list[dict[str, Any]],
    kinds: set[str],
    *,
    char_budget: int = 18000,
) -> str:
    """Project only evidence needed by one extractor while preserving source IDs."""
    selected: list[dict[str, Any]] = []
    for source in sources:
        kind = str(source.get("query_kind") or "unknown")
        if kind not in kinds:
            continue
        item = {
            key: source[key]
            for key in _SLICE_SOURCE_KEYS
            if source.get(key) not in (None, "", [], {})
        }
        selected.append(item)
    return json.dumps(
        selected,
        ensure_ascii=False,
        separators=(",", ":"),
    )[:char_budget]


def _to_fact(item: CompactCompanyFact) -> CompanyFact:
    return CompanyFact(
        field=item.field,
        value=item.value,
        period=item.period,
        confidence=item.confidence,
        source_ids=item.source_ids,
        note="",
    )


def _to_signal(item: CompactEconomicSignal) -> EconomicSignal:
    return EconomicSignal(
        signal=item.signal,
        evidence=item.evidence,
        business_effect=item.business_effect,
        confidence=item.confidence,
        source_ids=item.source_ids,
    )


def _unique_text(parts: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = " ".join(str(part).split()).strip()
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _merge_facts(*groups: list[CompactCompanyFact]) -> list[CompanyFact]:
    """Keep all distinct field/value facts but remove duplicate model phrasing."""
    result: list[CompanyFact] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for item in group:
            key = (item.field, " ".join(item.value.split()).casefold())
            if key in seen:
                continue
            seen.add(key)
            result.append(_to_fact(item))
    return result[:24]


async def extract_profile_parallel(
    *,
    request_json: RequestJson,
    url: str,
    title: str,
    text: str,
    external_sources: list[dict[str, Any]],
    accessed_at: str,
) -> MergedProfileExtraction:
    """Run bounded vertical extractors in parallel, then merge deterministically."""
    official_text = text[:12000]
    identity_context = _source_slice(external_sources, _IDENTITY_KINDS)
    operations_context = _source_slice(external_sources, _OPERATIONS_KINDS)
    signal_context = _source_slice(external_sources, _SIGNAL_KINDS)

    common_rules = """
Правила:
- S1 — официальный сайт; внешние источники имеют переданные id.
- Не создавай факты, цифры, людей, контакты или source_ids, которых нет во входе.
- Поисковый сниппет — сигнал, не проверенный первичный документ.
- Пиши кратко; не повторяй один факт разными словами.
- Если данных нет, пропусти факт, а не выдумывай его.
"""

    identity_prompt = f"""Извлеки identity/contact/ownership профиль компании.
Разрешённые поля: legal_name, brand_name, inn, ogrn, registration_status, address,
phones, emails, website, social_accounts, founders, executives, beneficial_owners,
affiliates, geography. Не извлекай финансовые показатели и коммерческое решение.
{common_rules}
URL: {url}
TITLE: {title}
ACCESSED AT: {accessed_at}
OFFICIAL PAGE TEXT:\n{official_text}
RELEVANT SOURCES:\n{identity_context}
"""

    operations_prompt = f"""Извлеки операционные и экономические факты компании.
Разрешённые поля: headcount, revenue, profit, assets, taxes, products, customers,
suppliers, other. Для финансовых значений обязательно указывай period, если он виден.
Не формируй economic_signals и не делай коммерческое предложение.
{common_rules}
URL: {url}
TITLE: {title}
OFFICIAL PAGE TEXT:\n{official_text}
RELEVANT SOURCES:\n{operations_context}
"""

    signal_prompt = f"""Извлеки только экономические/правовые/рыночные сигналы, которые
могут влиять на бизнес или AI-пилот. Для каждого сигнала дай короткое evidence,
business_effect и реальные source_ids. Не повторяй профиль компании.
{common_rules}
URL: {url}
TITLE: {title}
OFFICIAL PAGE TEXT:\n{official_text}
RELEVANT SOURCES:\n{signal_context}
"""

    identity, operations, signals = await asyncio.gather(
        request_json(
            "profile_identity",
            IdentityProfileSlice,
            system="Возвращай только компактный валидный JSON по схеме.",
            prompt=identity_prompt,
            max_tokens=1200,
            timeout_seconds=22.0,
        ),
        request_json(
            "profile_operations",
            OperationsProfileSlice,
            system="Возвращай только компактный валидный JSON по схеме.",
            prompt=operations_prompt,
            max_tokens=1100,
            timeout_seconds=22.0,
        ),
        request_json(
            "profile_signals",
            SignalProfileSlice,
            system="Возвращай только компактный валидный JSON по схеме.",
            prompt=signal_prompt,
            max_tokens=1000,
            timeout_seconds=22.0,
        ),
    )

    assert isinstance(identity, IdentityProfileSlice)
    assert isinstance(operations, OperationsProfileSlice)
    assert isinstance(signals, SignalProfileSlice)

    risks = _unique_text(
        identity.risks_and_assumptions
        + operations.risks_and_assumptions
        + signals.risks_and_assumptions,
        12,
    )
    return MergedProfileExtraction(
        company_name=identity.company_name,
        business_summary=identity.business_summary,
        evidence=_unique_text(identity.evidence, 5),
        company_facts=_merge_facts(identity.company_facts, operations.company_facts),
        economic_signals=[_to_signal(item) for item in signals.economic_signals[:6]],
        risks_and_assumptions=risks,
    )
