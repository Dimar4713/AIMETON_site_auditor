from __future__ import annotations

import asyncio

import app.routerai_split_v2 as split_v2
from app.models import (
    BusinessMachineCell,
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
    commercial_kwargs: dict = {}

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
        raise AssertionError(model_type)

    async def fake_strict_request(phase, model_type, **kwargs):
        phases.append(phase)
        commercial_kwargs.update(kwargs)
        if model_type is split_v2.CompactCommercialSynthesis:
            return split_v2.CompactCommercialSynthesis(
                commercial_opportunity=split_v2.CompactCommercialOpportunity(
                    opportunity_type="AI automation", problem_hypothesis="Manual process",
                    recommended_solution="AIMETON pilot", expected_value="Reduce manual work",
                    score=72, qualification="Перспективная",
                ),
                agents=[
                    split_v2.CompactAgentRecommendation(name="A1", purpose="Search", benefit="Speed"),
                    split_v2.CompactAgentRecommendation(name="A2", purpose="Analyze", benefit="Evidence"),
                    split_v2.CompactAgentRecommendation(name="A3", purpose="Report", benefit="Structure"),
                ],
                action_package=split_v2.CompactActionPackage(
                    decision_maker_hypothesis="Digital lead", contact_reason="Pilot",
                    demo_scenario=["Run audit"], first_message="Pilot proposal", next_action="Demo",
                ),
            )
        raise AssertionError(model_type)

    monkeypatch.setattr(split_v2, "extract_profile_parallel", fake_profile)
    monkeypatch.setattr(split_v2, "_request_json", fake_request)
    monkeypatch.setattr(split_v2, "request_json_strict", fake_strict_request)

    result = asyncio.run(
        split_v2.analyze_with_routerai_split_v2(
            "https://example.com",
            "Example",
            "Official text",
            [],
        )
    )

    assert set(phases) == {"km_reasoning", "commercial_reasoning"}
    assert commercial_kwargs["reasoning_effort"] == "high"
    assert commercial_kwargs["max_tokens"] == 1500
    assert commercial_kwargs["timeout_seconds"] == 25.0
    assert result.company_name == "Example"
    assert result.sources[0].id == "S1"
    assert result.business_machine_4x4[0].code == "III-III"
    assert result.commercial_opportunity.score == 72
    assert result.readiness.provider_states["routerai"] == "active"


def test_split_v2_commercial_envelope_is_bounded_and_expandable() -> None:
    schema = split_v2.CompactCommercialSynthesis.model_json_schema()
    assert schema["properties"]["agents"]["minItems"] == 3
    assert schema["properties"]["agents"]["maxItems"] == 5
    action_ref = schema["properties"]["action_package"]["$ref"].split("/")[-1]
    action_schema = schema["$defs"][action_ref]
    assert action_schema["properties"]["demo_scenario"]["maxItems"] == 3
    compact = split_v2.CompactCommercialSynthesis(
        commercial_opportunity=split_v2.CompactCommercialOpportunity(
            opportunity_type="AI audit", problem_hypothesis="Manual review",
            recommended_solution="Pilot", expected_value="Faster evidence",
            score=70, qualification="Перспективная",
        ),
        agents=[
            split_v2.CompactAgentRecommendation(name="A1", purpose="Search", benefit="Speed"),
            split_v2.CompactAgentRecommendation(name="A2", purpose="Analyze", benefit="Evidence"),
            split_v2.CompactAgentRecommendation(name="A3", purpose="Report", benefit="Structure"),
        ],
        action_package=split_v2.CompactActionPackage(
            decision_maker_hypothesis="Digital lead", contact_reason="Pilot",
            demo_scenario=["Run audit"], first_message="Pilot proposal", next_action="Demo",
        ),
    )
    expanded = split_v2._expand_commercial(compact)
    assert isinstance(expanded, CommercialSynthesis)
    assert len(expanded.agents) == 3
    assert expanded.commercial_opportunity.score == 70
