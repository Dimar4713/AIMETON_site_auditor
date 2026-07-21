from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import company_intelligence_runtime, discovery
from app.external_sources import classify_result, classify_source_domain, classification_state
from app.models import CompanyIntelligenceRequest, IntelligenceSource


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kimi_regression_cases.json"


def _cases() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases()["classification_cases"], ids=lambda case: case["id"])
def test_kimi_classification_golden_cases(case):
    source_class = classify_source_domain(case["url"], case["official_host"])
    result_kind = classify_result(case["title"], case["snippet"])
    state = classification_state(source_class, result_kind)

    assert source_class == case["expected_source_class"]
    assert result_kind == case["expected_result_kind"]
    assert state == case["expected_state"]


@pytest.mark.parametrize("case", _cases()["pre_score_cases"], ids=lambda case: case["id"])
def test_kimi_pre_score_golden_cases(case):
    request = discovery.HuntRequest(
        region=case["region"],
        focus=case["focus"],
        industries=["стоматология"],
    )
    result = discovery._pre_score(
        request,
        case["title"],
        case["snippet"],
        case["url"],
    )

    assert result.status == case["expected_status"]
    assert result.score == case["expected_score"]


def test_search_hint_is_not_evidence_by_default():
    source = IntelligenceSource(
        id="K1",
        title="Компания сообщила о росте выручки",
        url="https://news.example/article",
        snippet="Выручка выросла на 50%",
        accessed_at="2026-07-22T00:00:00+00:00",
        source_class="news",
        result_kind="finance",
        classification_state="ambiguous",
    )

    assert source.lifecycle_state == "discovery_hint"
    assert source.evidence_level == "unverified_mention"
    assert source.document_url is None
    assert source.evidence_quote is None


@pytest.mark.asyncio
async def test_company_intelligence_calls_external_provider_once_and_stays_partial_without_evidence(monkeypatch):
    calls = {"collect": 0}

    async def fake_collect(company_name, official_url, region, max_sources):
        calls["collect"] += 1
        return [
            IntelligenceSource(
                id="K1",
                title="Каталог компании",
                url="https://catalog.example/company",
                snippet="Поисковый сниппет",
                accessed_at="2026-07-22T00:00:00+00:00",
                source_class="unknown",
                query_kind="official",
                result_kind="unknown",
                classification_state="unknown",
                lifecycle_state="discovery_hint",
                evidence_level="unverified_mention",
            )
        ], []

    monkeypatch.setattr(company_intelligence_runtime, "collect_external_sources", fake_collect)

    result = await company_intelligence_runtime.run_company_intelligence(
        CompanyIntelligenceRequest(company_name="Тестовая компания", max_sources=5)
    )

    assert calls["collect"] == 1
    assert result.status == "partial"
    assert result.site_analysis is None
    assert result.sources[0].lifecycle_state == "discovery_hint"


def test_fixture_schema_changes_require_explicit_version_bump():
    fixture = _cases()
    assert fixture["schema_version"] == 1
    assert fixture["classification_cases"]
    assert fixture["pre_score_cases"]
