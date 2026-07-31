from __future__ import annotations

import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.search_gateway.factory import get_search_gateway, reset_search_gateway
from app.search_gateway.models import SearchRequest
from app.search_gateway.providers import YandexProvider


def _request() -> SearchRequest:
    return SearchRequest(
        query="AIMETON искусственный интеллект для бизнеса",
        limit=10,
        mission_id="mission-yandex-live-contract",
        correlation_id="correlation-yandex-live-contract",
    )


def test_gateway_factory_accepts_canonical_stage_folder_variable(monkeypatch):
    monkeypatch.setenv("YANDEX_SEARCH_API_KEY", "secret-yandex")
    monkeypatch.setenv("YANDEX_CLOUD_FOLDER_ID", "folder-stage")
    monkeypatch.delenv("YANDEX_SEARCH_FOLDER_ID", raising=False)
    monkeypatch.setenv("YANDEX_SEARCH_COST_RUB", "1")
    reset_search_gateway()

    gateway = get_search_gateway()
    health = {item.provider: item for item in gateway.health()}

    assert health["yandex"].configured is True
    reset_search_gateway()


def test_legacy_folder_variable_remains_compatible(monkeypatch):
    monkeypatch.setenv("YANDEX_SEARCH_API_KEY", "secret-yandex")
    monkeypatch.delenv("YANDEX_CLOUD_FOLDER_ID", raising=False)
    monkeypatch.setenv("YANDEX_SEARCH_FOLDER_ID", "folder-legacy")
    monkeypatch.setenv("YANDEX_SEARCH_COST_RUB", "1")
    reset_search_gateway()

    gateway = get_search_gateway()
    health = {item.provider: item for item in gateway.health()}

    assert health["yandex"].configured is True
    reset_search_gateway()


@pytest.mark.asyncio
async def test_yandex_gateway_payload_matches_accepted_stage_contract():
    xml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<yandexsearch><response><results><grouping><group><doc>"
        "<url>https://example.ru/about</url>"
        "<title>Example</title><passages><passage>Описание</passage></passages>"
        "</doc></group></grouping></results></response></yandexsearch>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["query"] == {
            "searchType": "SEARCH_TYPE_RU",
            "queryText": "AIMETON искусственный интеллект для бизнеса",
            "familyMode": "FAMILY_MODE_MODERATE",
            "page": "0",
            "fixTypoMode": "FIX_TYPO_MODE_ON",
        }
        assert payload["l10N"] == "LOCALIZATION_RU"
        assert "l10n" not in payload
        assert payload["responseFormat"] == "FORMAT_XML"
        assert payload["folderId"] == "folder-stage"
        return httpx.Response(
            200,
            json={"rawData": base64.b64encode(xml.encode()).decode()},
        )

    provider = YandexProvider(
        "secret-yandex",
        "folder-stage",
        cost_amount=Decimal("1"),
        transport=httpx.MockTransport(handler),
    )

    results = await provider.search(_request(), timeout_seconds=1)

    assert len(results) == 1
    assert results[0].provider == "yandex"
    assert str(results[0].url) == "https://example.ru/about"
