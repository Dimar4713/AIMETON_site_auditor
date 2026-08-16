from __future__ import annotations

import asyncio

import app.routerai_split_v2 as split_v2
from app.models import (
    ActionPackage,
    AgentRecommendation,
    BusinessMachineCell,
    CommercialOpportunity,
    CompanyFact,
    EconomicSignal,
)
from app.routerai_profile_extraction import MergedProfileExtraction
from app.routerai_split_synthesis import BusinessMachineSynthesis, CommercialSynthesis


def test_split_v2_uses_parallel_profile_then_existing_reasoning_and_assembler(monkeypatch) -> None:
    async def fake_profile(**kwargs):
        return MergedProfileExtraction(
            company_name="Example",
            business_summary="Engineering company",
            evidence=["Official evidence"],
            company_facts=[
                CompanyFact(
                    field="website",
                    value="https://example.com",
                    confidence="Высокая",
                    source_ids=["S1"],
                )
            ],
            economic_signals=[
                EconomicSignal(
                    signal="Automation signal",
                    evidence="Official process description",
                    business_effect="Potential pilot",
                    confidence="Средняя",
                    source_ids=["S1"],
                )
            ],
            risks_and_assumptions=[],
        )

    phases: list[str] = []

    async def fake_request(phase, model_type, **kwargs):
        phases.append(phase)
        if model_type is BusinessMachineSynthesis:
            return BusinessMachineSynthesis(
                business_machine_4x4=[
                    BusinessMachineCell(
                        code="III-III",
                        detail_operator="III — Технологии",
                        vertex="Рабочая процедура",
                        finding="Есть рабочий процесс",
                        status="Подтверждено",
                        confidence="Высокая",
                        source_ids=["S1"],
                        sales_relevance="Подходит для пилота",
                    )
                ]
            )
        if model_type is CommercialSynthesis:
            return CommercialSynthesis(
                commercial_opportunity=CommercialOpportunity(
                    opportunity_type="AI automation",
                    problem_hypothesis="Manual process",
                    recommended_solution="AIMETON pilot",
                    expected_value="Reduce manual work",
                    score=72,
                    qualification="Перспективная",
                ),
                agents=[
                    AgentRecommendation(name="A1", purpose="Search", benefit="Speed"),
                    AgentRecommendation(name="A2", purpose="Analyze", benefit="Evidence"),
                    AgentRecommendation(name="A3", purpose="Report", benefit="Structure"),
                ],
                action_package=ActionPackage(
                    decision_maker_hypothesis="Digital lead",
                    contact_reason="Pilot",
                    demo_scenario=["Run audit"],
                    first_message="Pilot proposal",
                    next_action="Demo",
                ),
            )
        raise AssertionError(model_type)

    monkeypatch.setattr(split_v2, "extract_profile_parallel", fake_profile)
    monkeypatch.setattr(split_v2, "_request_json", fake_request)

    result = asyncio.run(
        split_v2.analyze_with_routerai_split_v2(
            "https://example.com",
            "Example",
            "Official text",
            [],
        )
    )

    assert set(phases) == {"km_reasoning", "commercial_reasoning"}
    assert result.company_name == "Example"
    assert result.sources[0].id == "S1"
    assert result.business_machine_4x4[0].code == "III-III"
    assert result.commercial_opportunity.score == 72
    assert result.readiness.provider_states["routerai"] == "active"
