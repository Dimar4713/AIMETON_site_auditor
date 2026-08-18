from __future__ import annotations

import asyncio

import app.routerai_split_v2 as split_v2
from app.models import (
    BusinessMachineCell,
    CompanyFact,
    EconomicSignal,
)
from app.routerai_evidence_units import EvidenceCoverage
from app.routerai_profile_extraction import MergedProfileExtraction
from app.routerai_split_synthesis import BusinessMachineSynthesis, CommercialSynthesis


def _coverage() -> EvidenceCoverage:
    return EvidenceCoverage(
        official_chars_total=13,
        official_chunks_total=1,
        official_chunks_processed=1,
        sources_total=0,
        sources_processed=0,
        source_chunks_total=0,
        source_chunks_processed=0,
        extraction_units_total=5,
        extraction_units_processed=5,
        complete=True,
    )


def test_split_v2_stages_commercial_reasoning_then_deterministic_execution(monkeypatch) -> None:
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
            coverage=_coverage(),
        )

    phases: list[str] = []
    phase_kwargs: dict[str, dict] = {}

    async def fake_request(phase, model_type, **kwargs):
        phases.append(phase)
        phase_kwargs[phase] = kwargs
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
        phase_kwargs[phase] = kwargs
        if model_type is split_v2.CompactCommercialOpportunity:
            return split_v2.CompactCommercialOpportunity(
                opportunity_type="AI automation",
                problem_hypothesis="Manual process",
                recommended_solution="AIMETON pilot",
                expected_value="Reduce manual work",
                score=72,
                qualification="Перспективная",
            )
        if model_type is split_v2.CompactCommercialExecution:
            assert '"score":72' in kwargs["prompt"]
            return split_v2.CompactCommercialExecution(
                agents=[
                    split_v2.CompactAgentRecommendation(name="A1", purpose="Search", benefit="Speed"),
                    split_v2.CompactAgentRecommendation(name="A2", purpose="Analyze", benefit="Evidence"),
                    split_v2.CompactAgentRecommendation(name="A3", purpose="Report", benefit="Structure"),
                ],
                action_package=split_v2.CompactActionPackage(
                    decision_maker_hypothesis="Digital lead",
                    contact_reason="Pilot",
                    demo_scenario=["Run audit"],
                    first_message="Pilot proposal",
                    next_action="Demo",
                ),
            )
        raise AssertionError(model_type)

    monkeypatch.setattr(split_v2, "extract_profile_parallel", fake_profile)
    monkeypatch.setattr(split_v2, "persist_merged_evidence_ledger", lambda merged: None)
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

    assert set(phases) == {
        "km_reasoning",
        "commercial_opportunity_reasoning",
        "commercial_execution",
    }
    opportunity_kwargs = phase_kwargs["commercial_opportunity_reasoning"]
    assert opportunity_kwargs["reasoning_effort"] == "high"
    assert "reasoning_enabled" not in opportunity_kwargs
    assert opportunity_kwargs["max_tokens"] == 1500
    assert opportunity_kwargs["timeout_seconds"] == 25.0
    execution_kwargs = phase_kwargs["commercial_execution"]
    assert execution_kwargs["reasoning_enabled"] is False
    assert "reasoning_effort" not in execution_kwargs
    assert execution_kwargs["max_tokens"] == 1000
    assert execution_kwargs["timeout_seconds"] == 15.0
    assert "Engineering company" in opportunity_kwargs["prompt"]
    assert "Engineering company" in execution_kwargs["prompt"]
    assert result.company_name == "Example"
    assert result.sources[0].id == "S1"
    assert result.business_machine_4x4[0].code == "III-III"
    assert result.commercial_opportunity.score == 72
    assert result.readiness.provider_states["routerai"] == "active"


def test_full_reasoning_profile_has_no_legacy_30_fact_or_16_signal_cap() -> None:
    facts = [
        CompanyFact(field="other", value=f"fact-{index}", source_ids=["S1"])
        for index in range(75)
    ]
    signals = [
        EconomicSignal(
            signal=f"signal-{index}",
            evidence=f"evidence-{index}",
            business_effect=f"effect-{index}",
            source_ids=["S1"],
        )
        for index in range(40)
    ]
    merged = MergedProfileExtraction(
        company_name="Large Co",
        business_summary="Large dossier",
        evidence=[f"evidence-item-{index}" for index in range(25)],
        company_facts=facts,
        economic_signals=signals,
        risks_and_assumptions=[f"risk-{index}" for index in range(20)],
        coverage=_coverage(),
    )

    reasoning = split_v2._full_reasoning_profile(merged)

    assert len(reasoning.company_facts) == 75
    assert reasoning.company_facts[-1].value == "fact-74"
    assert len(reasoning.economic_signals) == 40
    assert reasoning.economic_signals[-1].signal == "signal-39"
    assert len(reasoning.evidence) == 25
    assert reasoning.coverage["complete"] is True


def test_split_v2_commercial_envelopes_are_bounded_and_expandable() -> None:
    execution_schema = split_v2.CompactCommercialExecution.model_json_schema()
    assert execution_schema["properties"]["agents"]["minItems"] == 3
    assert execution_schema["properties"]["agents"]["maxItems"] == 5
    action_ref = execution_schema["properties"]["action_package"]["$ref"].split("/")[-1]
    action_schema = execution_schema["$defs"][action_ref]
    assert action_schema["properties"]["demo_scenario"]["maxItems"] == 3
    opportunity = split_v2.CompactCommercialOpportunity(
        opportunity_type="AI audit",
        problem_hypothesis="Manual review",
        recommended_solution="Pilot",
        expected_value="Faster evidence",
        score=70,
        qualification="Перспективная",
    )
    execution = split_v2.CompactCommercialExecution(
        agents=[
            split_v2.CompactAgentRecommendation(name="A1", purpose="Search", benefit="Speed"),
            split_v2.CompactAgentRecommendation(name="A2", purpose="Analyze", benefit="Evidence"),
            split_v2.CompactAgentRecommendation(name="A3", purpose="Report", benefit="Structure"),
        ],
        action_package=split_v2.CompactActionPackage(
            decision_maker_hypothesis="Digital lead",
            contact_reason="Pilot",
            demo_scenario=["Run audit"],
            first_message="Pilot proposal",
            next_action="Demo",
        ),
    )
    expanded = split_v2._expand_commercial(opportunity, execution)
    assert isinstance(expanded, CommercialSynthesis)
    assert len(expanded.agents) == 3
    assert expanded.commercial_opportunity.score == 70
