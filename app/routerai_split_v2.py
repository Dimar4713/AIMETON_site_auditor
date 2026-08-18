from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import CompanyFact, EconomicSignal, SiteAnalysis
from app.routerai_evidence_ledger import persist_merged_evidence_ledger
from app.routerai_profile_extraction import extract_profile_parallel
from app.routerai_split_synthesis import (
    BusinessMachineSynthesis,
    CommercialSynthesis,
    _assemble_site_analysis,
    _request_json,
)
from app.routerai_strict_request import request_json_strict


CompactText80 = Annotated[str, Field(max_length=80)]
CompactText140 = Annotated[str, Field(max_length=140)]
CompactText180 = Annotated[str, Field(max_length=180)]
CompactText220 = Annotated[str, Field(max_length=220)]


class FullReasoningProfile(BaseModel):
    """Internal split-v2 profile: preserve the complete merged evidence ledger."""

    company_name: str
    business_summary: str
    evidence: list[str] = Field(default_factory=list)
    company_facts: list[CompanyFact] = Field(default_factory=list)
    economic_signals: list[EconomicSignal] = Field(default_factory=list)
    risks_and_assumptions: list[str] = Field(default_factory=list)
    coverage: dict[str, int | bool] = Field(default_factory=dict)


class CompactCommercialOpportunity(BaseModel):
    opportunity_type: CompactText80
    problem_hypothesis: CompactText220
    recommended_solution: CompactText220
    expected_value: CompactText180
    score: int = Field(ge=0, le=100)
    qualification: Literal["Приоритетная", "Перспективная", "Наблюдение", "Недостаточно данных"]


class CompactAgentRecommendation(BaseModel):
    name: CompactText80
    purpose: CompactText140
    benefit: CompactText140
    priority: Literal["Высокий", "Средний", "Низкий"] = "Средний"


class CompactActionPackage(BaseModel):
    decision_maker_hypothesis: CompactText140
    contact_reason: CompactText180
    demo_scenario: list[CompactText140] = Field(default_factory=list, max_length=3)
    first_message: CompactText220
    next_action: CompactText140


class CompactCommercialSynthesis(BaseModel):
    commercial_opportunity: CompactCommercialOpportunity
    agents: list[CompactAgentRecommendation] = Field(min_length=3, max_length=5)
    action_package: CompactActionPackage


def _expand_commercial(compact: CompactCommercialSynthesis) -> CommercialSynthesis:
    return CommercialSynthesis.model_validate(compact.model_dump(mode="python"))


def _full_reasoning_profile(merged) -> FullReasoningProfile:
    return FullReasoningProfile(
        company_name=merged.company_name,
        business_summary=merged.business_summary,
        evidence=merged.evidence,
        company_facts=merged.company_facts,
        economic_signals=merged.economic_signals,
        risks_and_assumptions=merged.risks_and_assumptions,
        coverage=merged.coverage.safe_dict(),
    )


async def analyze_with_routerai_split_v2(
    url: str,
    title: str,
    text: str,
    external_sources: list[dict] | None = None,
) -> SiteAnalysis:
    """Coverage-preserving extraction → durable ledger → reasoning → assembly."""
    external_sources = external_sources or []
    accessed_at = datetime.now(timezone.utc).isoformat()

    merged = await extract_profile_parallel(
        request_json=_request_json,
        strict_request_json=request_json_strict,
        url=url,
        title=title,
        text=text,
        external_sources=external_sources,
        accessed_at=accessed_at,
    )
    # Durability is an admission gate for mission-bound reasoning. Direct calls have no
    # trace identity and intentionally skip persistence.
    persist_merged_evidence_ledger(merged)

    profile = _full_reasoning_profile(merged)
    profile_context = json.dumps(
        profile.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    km_prompt = f"""Построй каноническую бизнес-модель AIMETON / КМ только из
извлечённого профиля ниже. Сформируй до 16 ячеек. Не создавай факты сверх
профиля. Для каждой ячейки укажи finding, status, confidence, source_ids и
sales_relevance.

Канон:
I-I Взаимодействие; I-II Влияние; I-III Зависимость; I-IV Противодействие.
II-I Учредители и собственники; II-II Ось люди-управленцы;
II-III Обслуживающий персонал и роботы; II-IV Виртуозы и специалисты.
III-I Знания и наука; III-II Стандартная процедура; III-III Рабочая процедура;
III-IV Продукты, товар и услуга.
IV-I Управление коммуникационными системами; IV-II Управление людьми;
IV-III Управление технологиями; IV-IV Самоуправление.
Если данных нет, используй status=\"Нет данных\" и не компенсируй пробелы
фантазией. Coverage metadata — только агрегаты полноты, не факты компании.
Пиши кратко.

EXTRACTED PROFILE:\n{profile_context}
"""

    commercial_prompt = f"""Ты — AI-продажник AIMETON. На основе только
извлечённого профиля выбери одну наиболее доказанную коммерческую AI-возможность.
Сначала учитывай подтверждённые экономические сигналы и пробелы, затем предложи
реалистичное решение, 3–5 AI-агентов/инструментов и компактный пакет первого контакта.
Оценка 80+ допустима только при прямом подтверждении проблемы, масштаба и
реалистичного пилота. Не обещай неподтверждённый эффект. Coverage metadata
используй только чтобы понимать полноту входа. Пиши кратко.

EXTRACTED PROFILE:\n{profile_context}
"""

    km_result, commercial_result = await asyncio.gather(
        _request_json(
            "km_reasoning",
            BusinessMachineSynthesis,
            system="Возвращай только компактный валидный JSON по схеме и соблюдай канонические коды КМ.",
            prompt=km_prompt,
            max_tokens=2500,
            timeout_seconds=25.0,
        ),
        request_json_strict(
            "commercial_reasoning",
            CompactCommercialSynthesis,
            system="Возвращай только компактный валидный JSON по схеме. Главный результат — доказанная коммерческая возможность.",
            prompt=commercial_prompt,
            max_tokens=1500,
            timeout_seconds=25.0,
            reasoning_effort="high",
        ),
    )

    return _assemble_site_analysis(
        url=url,
        title=title,
        text=text,
        external_sources=external_sources,
        profile=profile,
        km=km_result,
        commercial=_expand_commercial(commercial_result),
        accessed_at=accessed_at,
    )
