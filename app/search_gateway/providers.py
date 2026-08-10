from __future__ import annotations

import base64
import hashlib
import html
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        reason: FallbackReason = FallbackReason.PROVIDER_ERROR,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.reason = reason


@dataclass(frozen=True)
class ProviderDegradation:
    reason: FallbackReason
    upstreams: tuple[str, ...]


class SearchProvider(ABC):
    name: str
    paid: bool
    cost_amount: Decimal
    cost_currency: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @property
    def execution_allowed(self) -> bool:
        """Whether the provider may execute in this deployment context."""
        return True

    @property
    def execution_block_reason(self) -> FallbackReason | None:
        return None

    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:
        return None

    @abstractmethod
    async def search(
        self,
        request: SearchRequest,
        *,
        timeout_seconds: float,
    ) -> list[SearchItem]: ...


class HttpSearchProvider(SearchProvider):
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self._transport = transport
        self._proxy_url = (proxy_url or "").strip() or None

    @property
    def proxy_configured(self) -> bool:
        return bool(self._proxy_url)

    @staticmethod
    def _http_failure_reason(response: httpx.Response) -> FallbackReason:
        body_hint = response.text[:2000].casefold()
        if "captcha" in body_hint or "recaptcha" in body_hint:
            return FallbackReason.CAPTCHA
        if response.status_code == 429:
            return FallbackReason.RATE_LIMITED
        if response.status_code in {401, 403}:
            return FallbackReason.PROVIDER_BLOCKED
        return FallbackReason.PROVIDER_ERROR

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client_kwargs: dict[str, Any] = {
            "timeout": timeout_seconds,
            "follow_redirects": True,
        }
        if self._transport is not None:
            # Mock/custom transports own routing during tests and specialized use.
            client_kwargs["transport"] = self._transport
        elif self._proxy_url:
            # Explicit provider-local egress. The URL is intentionally never
            # copied into ProviderError/diagnostics so credentials cannot leak.
            client_kwargs["proxy"] = self._proxy_url
            client_kwargs["trust_env"] = False

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"{self.name} timeout",
                retryable=True,
                reason=FallbackReason.TIMEOUT,
            ) from exc
        except httpx.HTTPStatusError as exc:
            reason = self._http_failure_reason(exc.response)
            retryable = reason not in {
                FallbackReason.RATE_LIMITED,
                FallbackReason.PROVIDER_BLOCKED,
                FallbackReason.CAPTCHA,
            }
            raise ProviderError(
                f"{self.name} http {exc.response.status_code}",
                retryable=retryable,
                reason=reason,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self.name} request failed",
                retryable=True,
                reason=FallbackReason.PROVIDER_ERROR,
            ) from exc
        except ValueError as exc:
            raise ProviderError(
                f"{self.name} invalid json payload",
                retryable=False,
                reason=FallbackReason.PROTOCOL_ERROR,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                f"{self.name} returned an invalid payload",
                retryable=False,
                reason=FallbackReason.PROTOCOL_ERROR,
            )
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
        engines: tuple[str, ...] = (),
        engine_fanout: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(transport=transport)
        self._base_url = (base_url or "").strip().rstrip("/")
        self._engines = tuple(item.strip() for item in engines if item.strip())
        self._engine_fanout = max(1, int(engine_fanout)) if engine_fanout is not None else None
        self._degradations: dict[int, ProviderDegradation] = {}

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    def _engines_for_request(self, request: SearchRequest) -> tuple[str, ...]:
        if not self._engines:
            return ()
        if self._engine_fanout is None or self._engine_fanout >= len(self._engines):
            return self._engines
        seed = "\n".join((" ".join(request.query.split()).casefold(), request.language.casefold()))
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        start = int.from_bytes(digest[:8], "big") % len(self._engines)
        return tuple(
            self._engines[(start + offset) % len(self._engines)]
            for offset in range(self._engine_fanout)
        )

    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:
        return self._degradations.pop(id(request), None)

    @staticmethod
    def _classify_unresponsive(unresponsive: object) -> ProviderDegradation | None:
        if not isinstance(unresponsive, list) or not unresponsive:
            return None
        failed_names: list[str] = []
        failure_text: list[str] = []
        for item in unresponsive[:16]:
            if isinstance(item, (list, tuple)) and item:
                name = str(item[0]).strip()
                if name and name not in failed_names:
                    failed_names.append(name)
                failure_text.extend(str(part) for part in item[1:])
            elif isinstance(item, str):
                name = item.strip()
                if name and name not in failed_names:
                    failed_names.append(name)
                failure_text.append(item)
        diagnostic = " ".join(failure_text).casefold()
        if "captcha" in diagnostic or "recaptcha" in diagnostic:
            reason = FallbackReason.CAPTCHA
        elif "too many" in diagnostic or "429" in diagnostic or "rate" in diagnostic:
            reason = FallbackReason.RATE_LIMITED
        elif "access denied" in diagnostic or "403" in diagnostic or "forbidden" in diagnostic:
            reason = FallbackReason.PROVIDER_BLOCKED
        elif "protocol" in diagnostic or "parse" in diagnostic:
            reason = FallbackReason.PROTOCOL_ERROR
        else:
            reason = FallbackReason.PROVIDER_ERROR
        return ProviderDegradation(reason=reason, upstreams=tuple(failed_names))

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        self._degradations.pop(id(request), None)
        params: dict[str, str | int] = {
            "q": request.query,
            "format": "json",
            "language": request.language,
            "safesearch": 1,
        }
        selected_engines = self._engines_for_request(request)
        if selected_engines:
            params["engines"] = ",".join(selected_engines)

        payload = await self._request_json(
            "GET",
            f"{self._base_url}/search",
            timeout_seconds=timeout_seconds,
            params=params,
        )
        results = [
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

        degradation = self._classify_unresponsive(payload.get("unresponsive_engines") or [])
        if degradation is not None:
            if results:
                self._degradations[id(request)] = degradation
            else:
                suffix = f" ({', '.join(degradation.upstreams)})" if degradation.upstreams else ""
                raise ProviderError(
                    f"searxng upstream engines unavailable{suffix}",
                    retryable=degradation.reason is FallbackReason.PROVIDER_ERROR,
                    reason=degradation.reason,
                )
        return results


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
        proxy_url: str | None = None,
        contract_allowed: bool = True,
    ) -> None:
        super().__init__(transport=transport, proxy_url=proxy_url)
        self._api_key = (api_key or "").strip()
        self._contract_allowed = bool(contract_allowed)
        self.cost_amount = cost_amount

    @property
    def technical_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def contract_allowed(self) -> bool:
        return self._contract_allowed

    @property
    def configured(self) -> bool:
        # `configured` reports technical configuration only. Eligibility is a
        # separate dimension so health/trace can distinguish a missing key from
        # a contract restriction.
        return self.technical_configured

    @property
    def execution_allowed(self) -> bool:
        return self._contract_allowed

    @property
    def execution_block_reason(self) -> FallbackReason | None:
        return None if self._contract_allowed else FallbackReason.CONTRACT_BLOCKED

    async def search(self, request: SearchRequest, *, timeout_seconds: float) -> list[SearchItem]:
        if not self._contract_allowed:
            raise ProviderError(
                "tavily execution is not permitted for this deployment context",
                retryable=False,
                reason=FallbackReason.CONTRACT_BLOCKED,
            )
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
            raise ProviderError(
                "yandex returned no rawData",
                retryable=False,
                reason=FallbackReason.PROTOCOL_ERROR,
            )
        try:
            xml_text = base64.b64decode(raw_data, validate=True).decode("utf-8")
            root = ET.fromstring(xml_text)
        except (ValueError, UnicodeDecodeError, ET.ParseError) as exc:
            raise ProviderError(
                "yandex returned invalid XML data",
                retryable=False,
                reason=FallbackReason.PROTOCOL_ERROR,
            ) from exc
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
