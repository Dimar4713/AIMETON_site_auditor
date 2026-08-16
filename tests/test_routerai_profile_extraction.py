from __future__ import annotations

import asyncio
import json

import app.routerai_profile_extraction as profile
from app.models import CompanyFact


def _source(source_id: str, query_kind: str) -> dict:
    return {
        "id": source_id,
        "title": f"Source {source_id}",
        "query_kind": query_kind,
        "source_class": query_kind,
        "evidence_level": "unverified_mention",
        "snippet": f"snippet-{source_id}",
        "url": f"https://example.test/{source_id}",
    }


def test_source_slices_follow_search_verticals_and_keep_ids() -> None:
    sources = [
        _source("E1", "contact"),
        _source("E2", "ownership"),
        _source("E3", "affiliation"),
        _source("E4", "finance"),
        _source("E5", "court"),
        _source("E6", "jobs"),
    ]

    identity_core = json.loads(
        profile._source_slice(sources, profile._IDENTITY_CORE_KINDS)
    )
    management = json.loads(profile._source_slice(sources, profile._MANAGEMENT_KINDS))
    ownership_network = json.loads(
        profile._source_slice(sources, profile._OWNERSHIP_NETWORK_KINDS)
    )
    operations = json.loads(profile._source_slice(sources, profile._OPERATIONS_KINDS))
    signals = json.loads(profile._source_slice(sources, profile._SIGNAL_KINDS))

    assert {item["id"] for item in identity_core} == {"E1"}
    assert {item["id"] for item in management} == {"E2"}
    assert {item["id"] for item in ownership_network} == {"E2", "E3"}
    assert {item["id"] for item in operations} == {"E4", "E6"}
    assert {item["id"] for item in signals} == {"E4", "E5"}
    assert all(
        "url" not in item
        for item in identity_core + management + ownership_network + operations + signals
    )


def test_vertical_dto_bounds_are_materially_smaller_than_monolith() -> None:
    fact_schema = profile.CompactCompanyFact.model_json_schema()
    signal_schema = profile.CompactEconomicSignal.model_json_schema()
    identity_schema = profile.IdentityCoreSlice.model_json_schema()
    management_schema = profile.ManagementSlice.model_json_schema()
    ownership_schema = profile.OwnershipNetworkSlice.model_json_schema()
    operations_schema = profile.OperationsProfileSlice.model_json_schema()
    signal_slice_schema = profile.SignalProfileSlice.model_json_schema()

    assert fact_schema["properties"]["value"]["maxLength"] == 200
    assert fact_schema["properties"]["source_ids"]["maxItems"] == 3
    assert signal_schema["properties"]["signal"]["maxLength"] == 140
    assert signal_schema["properties"]["business_effect"]["maxLength"] == 170
    assert signal_schema["properties"]["source_ids"]["maxItems"] == 3
    assert identity_schema["properties"]["company_facts"]["maxItems"] == 9
    assert management_schema["properties"]["company_facts"]["maxItems"] == 2
    assert management_schema["properties"]["risks_and_assumptions"]["maxItems"] == 1
    assert ownership_schema["properties"]["company_facts"]["maxItems"] == 3
    assert ownership_schema["properties"]["risks_and_assumptions"]["maxItems"] == 2
    assert operations_schema["properties"]["company_facts"]["maxItems"] == 9
    assert signal_slice_schema["properties"]["economic_signals"]["maxItems"] == 6


def test_parallel_extractors_merge_into_public_fact_models() -> None:
    phases: list[tuple[str, int]] = []

    async def fake_request(phase, model_type, **kwargs):
        phases.append((phase, kwargs["max_tokens"]))
        if model_type is profile.IdentityCoreSlice:
            return profile.IdentityCoreSlice(
                company_name="Example",
                business_summary="Engineering company",
                evidence=["Official site identifies the company"],
                company_facts=[
                    profile.CompactCompanyFact(
                        field="website",
                        value="https://example.com",
                        confidence="Высокая",
                        source_ids=["S1"],
                    )
                ],
                risks_and_assumptions=["Identity needs registry confirmation"],
            )
        if model_type is profile.ManagementSlice:
            return profile.ManagementSlice(
                company_facts=[
                    profile.CompactCompanyFact(
                        field="executives",
                        value="Named executive",
                        confidence="Средняя",
                        source_ids=["E2"],
                    )
                ]
            )
        if model_type is profile.OwnershipNetworkSlice:
            return profile.OwnershipNetworkSlice(
                company_facts=[
                    profile.CompactCompanyFact(
                        field="affiliates",
                        value="Related company hypothesis",
                        confidence="Низкая",
                        source_ids=["E3"],
                    )
                ]
            )
        if model_type is profile.OperationsProfileSlice:
            return profile.OperationsProfileSlice(
                company_facts=[
                    profile.CompactCompanyFact(
                        field="products",
                        value="Engineering services",
                        confidence="Средняя",
                        source_ids=["E4"],
                    )
                ]
            )
        if model_type is profile.SignalProfileSlice:
            return profile.SignalProfileSlice(
                economic_signals=[
                    profile.CompactEconomicSignal(
                        signal="Market signal",
                        evidence="Court or finance mention",
                        business_effect="Possible automation demand",
                        confidence="Средняя",
                        source_ids=["E5"],
                    )
                ]
            )
        raise AssertionError(model_type)

    merged = asyncio.run(
        profile.extract_profile_parallel(
            request_json=fake_request,
            url="https://example.com",
            title="Example",
            text="Official site text",
            external_sources=[
                _source("E1", "contact"),
                _source("E2", "ownership"),
                _source("E3", "affiliation"),
                _source("E4", "other"),
                _source("E5", "court"),
            ],
            accessed_at="2026-08-16T00:00:00+00:00",
        )
    )

    assert {phase for phase, _ in phases} == {
        "profile_identity_core",
        "profile_management",
        "profile_ownership_network",
        "profile_operations",
        "profile_signals",
    }
    phase_tokens = dict(phases)
    assert phase_tokens["profile_management"] == 600
    assert phase_tokens["profile_ownership_network"] == 700
    assert max(phase_tokens.values()) <= 1100
    assert merged.company_name == "Example"
    assert all(isinstance(item, CompanyFact) for item in merged.company_facts)
    assert {item.field for item in merged.company_facts} == {
        "website",
        "executives",
        "affiliates",
        "products",
    }
    assert merged.economic_signals[0].source_ids == ["E5"]
    assert merged.risks_and_assumptions == ["Identity needs registry confirmation"]
