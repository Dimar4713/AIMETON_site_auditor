import base64

import httpx

from app.search_providers.yandex_web import YandexWebSearchProvider


XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<yandexsearch><response><results><grouping><group><doc>
<url>https://example.org/company</url><title>Example Company</title>
<passages><passage>Company profile and contacts</passage></passages>
</doc></group></grouping></results></response></yandexsearch>'''


def test_health_is_not_configured_without_credentials(monkeypatch):
    monkeypatch.delenv("YANDEX_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_CLOUD_FOLDER_ID", raising=False)
    health = YandexWebSearchProvider().health()
    assert health.state == "not_configured"
    assert health.secrets_exposed is False


def test_search_normalizes_xml_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Api-Key test-key"
        payload = __import__("json").loads(request.content)
        assert payload["folderId"] == "folder-id"
        assert payload["query"]["searchType"] == "ru"
        return httpx.Response(200, json={"rawData": base64.b64encode(XML).decode()})

    provider = YandexWebSearchProvider(
        api_key="test-key",
        folder_id="folder-id",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.search("example company")
    assert result.state == "resolved"
    assert result.authority_verified is False
    assert len(result.records) == 1
    assert result.records[0].host == "example.org"
    assert result.records[0].rank == 1
    assert result.records[0].response_digest.startswith("sha256:")


def test_site_filter_is_injected_into_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"rawData": base64.b64encode(XML).decode()})

    provider = YandexWebSearchProvider(
        api_key="test-key",
        folder_id="folder-id",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.search("contacts", site="example.org")
    assert seen["query"]["queryText"] == "site:example.org contacts"
