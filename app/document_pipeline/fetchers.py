from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.scraper import (
    BROWSER_HEADERS,
    FetchError,
    _fetch_via_browser,
    _validate_public_url,
)


ALLOWED_HTML_TYPES = {"text/html", "application/xhtml+xml"}


@dataclass(frozen=True)
class RawDocument:
    final_url: str
    title: str
    html: str
    media_type: str
    path: str


class DynamicFetcher(ABC):
    name: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def fetch(self, url: str, *, timeout_seconds: float) -> RawDocument: ...


class StaticHttpFetcher:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int,
    ) -> RawDocument:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout_seconds,
            headers=BROWSER_HEADERS,
            transport=self._transport,
        ) as client:
            current = url
            for _ in range(max_redirects + 1):
                _validate_public_url(current)
                try:
                    async with client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise FetchError("Сайт вернул некорректное перенаправление")
                            current = str(httpx.URL(current).join(location))
                            continue
                        if response.status_code >= 400:
                            raise FetchError(f"Сайт вернул ошибку HTTP {response.status_code}")

                        media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                        if media_type not in ALLOWED_HTML_TYPES:
                            raise FetchError("Документ не является разрешённым HTML")

                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise FetchError("Документ превышает допустимый размер")
                            chunks.append(chunk)
                        html = b"".join(chunks).decode(
                            response.encoding or "utf-8",
                            errors="replace",
                        )
                        return RawDocument(
                            final_url=str(response.url),
                            title="",
                            html=html,
                            media_type=media_type,
                            path="static",
                        )
                except httpx.TimeoutException as exc:
                    raise FetchError("Истекло время загрузки документа") from exc
                except httpx.HTTPError as exc:
                    raise FetchError("Ошибка загрузки документа") from exc
        raise FetchError("Слишком много перенаправлений")


class Crawl4AIHttpWorker(DynamicFetcher):
    name = "crawl4ai"

    def __init__(
        self,
        base_url: str | None,
        *,
        api_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or "").strip().rstrip("/")
        self._api_token = (api_token or "").strip()
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    async def fetch(self, url: str, *, timeout_seconds: float) -> RawDocument:
        if not self.configured:
            raise FetchError("Crawl4AI worker не настроен")
        _validate_public_url(url)
        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/crawl",
                    headers=(
                        {"Authorization": f"Bearer {self._api_token}"}
                        if self._api_token
                        else None
                    ),
                    json={
                        "urls": [url],
                        "browser_config": {
                            "type": "BrowserConfig",
                            "params": {"headless": True},
                        },
                        "crawler_config": {
                            "type": "CrawlerRunConfig",
                            "params": {
                                "stream": False,
                                "cache_mode": "enabled",
                            },
                        },
                    },
                )
                response.raise_for_status()
                payload: Any = response.json()
        except httpx.TimeoutException as exc:
            raise FetchError("Истекло время Crawl4AI worker") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise FetchError("Crawl4AI worker недоступен") from exc

        result: Any = payload
        if isinstance(payload, dict):
            result = (
                payload.get("results")
                or payload.get("result")
                or payload.get("data")
                or payload
            )
        if isinstance(result, list):
            result = result[0] if result else {}
        if isinstance(result, dict) and isinstance(result.get("result"), dict):
            result = result["result"]
        if not isinstance(result, dict) or result.get("success") is False:
            raise FetchError("Crawl4AI worker не смог извлечь документ")
        html = result.get("cleaned_html") or result.get("html")
        final_url = result.get("url") or url
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        if not isinstance(html, str) or not html.strip():
            raise FetchError("Crawl4AI worker не вернул HTML")
        _validate_public_url(str(final_url))
        return RawDocument(
            final_url=str(final_url),
            title=str(result.get("title") or metadata.get("title") or ""),
            html=html,
            media_type="text/html",
            path=self.name,
        )


class PlaywrightFallback(DynamicFetcher):
    name = "browser"

    @property
    def configured(self) -> bool:
        return True

    async def fetch(self, url: str, *, timeout_seconds: float) -> RawDocument:
        del timeout_seconds
        final_url, title, html = await _fetch_via_browser(url)
        return RawDocument(
            final_url=final_url,
            title=title,
            html=html,
            media_type="text/html",
            path=self.name,
        )
