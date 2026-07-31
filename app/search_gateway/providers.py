from __future__ import annotations

import base64
import html
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import httpx

from app.search_gateway.models import SearchItem, SearchRequest


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class SearchProvider(ABC):
    name: str
    paid: bool
    cost_amount: Decimal
    cost_currency: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def search(
        self,
        request: SearchRequest,
        *,
        timeout_seconds: float,
    ) -> list[SearchItem]: ...


class HttpSearchProvider(SearchProvider):
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                follow_redirects=True,
                transport=self._transport,
            ) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name} timeout") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"{self.name} request failed") from exc
        if not isinstance(payload, dict):
            raise ProviderError(f"{self.name} returned an invalid payload", retryable=False)
        return payload


class SearxngProvider(HttpSearchProvider):
    name = "searxng"
    paid = False
    cost_amount = Decimal("0")
    cost_currency = "USD"

    def __init__(
        self,
        base_url: str | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._base_url = (base_url or "").strip().rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        payload = await self._request_json(
            "GET",
            f"{self._base_url}/search",
            timeout_seconds=timeout_seconds,
            params={
                "q": request.query,
                "format": "json",
                "language": request.language,
                "safesearch": 1,
            },
        )
        return [
            SearchItem(
                url=item["url"],
                title=str(item.get("title") or ""),
                snippet=str(item.get("content") or item.get("snippet") or ""),
                published_at=item.get("publishedDate"),
                provider=self.name,
            )
            for item in payload.get("results", [])
            if isinstance(item, dict) and item.get("url")
        ][: request.limit]


class TavilyProvider(HttpSearchProvider):
    name = "tavily"
    paid = True
    cost_currency = "USD"

    def __init__(
        self,
        api_key: str | None,
        *,
        cost_amount: Decimal = Decimal("0"),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._api_key = (api_key or "").strip()
        self.cost_amount = cost_amount

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        payload = await self._request_json(
            "POST",
            "https://api.tavily.com/search",
            timeout_seconds=timeout_seconds,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "query": request.query,
                "search_depth": "basic",
                "max_results": min(request.limit, 20),
                "include_answer": False,
                "include_raw_content": False,
            },
        )
        return [
            SearchItem(
                url=item["url"],
                title=str(item.get("title") or ""),
                snippet=str(item.get("content") or ""),
                published_at=item.get("published_date"),
                provider=self.name,
            )
            for item in payload.get("results", [])
            if isinstance(item, dict) and item.get("url")
        ][: request.limit]


class YandexProvider(HttpSearchProvider):
    name = "yandex"
    paid = True
    cost_currency = "RUB"

    def __init__(
        self,
        api_key: str | None,
        folder_id: str | None,
        *,
        cost_amount: Decimal = Decimal("0"),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._api_key = (api_key or "").strip()
        self._folder_id = (folder_id or "").strip()
        self.cost_amount = cost_amount

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._folder_id)

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        payload = await self._request_json(
            "POST",
            "https://searchapi.api.cloud.yandex.net/v2/web/search",
            timeout_seconds=timeout_seconds,
            headers={"Authorization": f"Api-Key {self._api_key}"},
            json={
                "query": {
                    "searchType": "SEARCH_TYPE_RU",
                    "queryText": request.query,
                    "familyMode": "FAMILY_MODE_MODERATE",
                    "page": "0",
                    "fixTypoMode": "FIX_TYPO_MODE_ON",
                },
                "groupSpec": {
                    "groupMode": "GROUP_MODE_FLAT",
                    "groupsOnPage": str(min(request.limit, 100)),
                    "docsInGroup": "1",
                },
                "maxPassages": "3",
                "l10N": "LOCALIZATION_RU",
                "folderId": self._folder_id,
                "responseFormat": "FORMAT_XML",
            },
        )
        raw_data = payload.get("rawData")
        if not isinstance(raw_data, str):
            raise ProviderError("yandex returned no rawData", retryable=False)
        try:
            xml_text = base64.b64decode(raw_data, validate=True).decode("utf-8")
            root = ET.fromstring(xml_text)
        except (ValueError, UnicodeDecodeError, ET.ParseError) as exc:
            raise ProviderError("yandex returned invalid XML data", retryable=False) from exc
        results: list[SearchItem] = []
        for document in root.findall(".//doc"):
            url = document.findtext("url")
            if not url:
                continue
            passages = [
                "".join(passage.itertext())
                for passage in document.findall(".//passage")
            ]
            results.append(
                SearchItem(
                    url=url,
                    title=html.unescape("".join(document.find("title").itertext()))
                    if document.find("title") is not None
                    else "",
                    snippet=html.unescape(" ".join(passages)),
                    provider=self.name,
                )
            )
        return results[: request.limit]
