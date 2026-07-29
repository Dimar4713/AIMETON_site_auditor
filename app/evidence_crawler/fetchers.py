from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.document_pipeline.fetchers import decode_html_bytes
from app.scraper import BROWSER_HEADERS, FetchError, _validate_public_url


ALLOWED_METADATA_TYPES = {
    "application/xml",
    "application/xhtml+xml",
    "text/plain",
    "text/xml",
}


def _allowlist_key(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        return f"{host}:{port}"
    return host


@dataclass(frozen=True)
class MetadataResponse:
    status_code: int
    final_url: str
    text: str
    media_type: str


class MetadataFetcher(ABC):
    @abstractmethod
    async def fetch_text(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int = 4,
        allowed_hosts: frozenset[str] = frozenset(),
    ) -> MetadataResponse: ...


class StaticMetadataFetcher(MetadataFetcher):
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_text(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int = 4,
        allowed_hosts: frozenset[str] = frozenset(),
    ) -> MetadataResponse:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout_seconds,
            headers=BROWSER_HEADERS,
            transport=self._transport,
        ) as client:
            current = url
            for _ in range(max_redirects + 1):
                _validate_public_url(current)
                if allowed_hosts and _allowlist_key(current) not in allowed_hosts:
                    raise FetchError("Metadata redirect нарушает domain allowlist")
                try:
                    async with client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise FetchError(
                                    "Metadata вернул некорректное перенаправление"
                                )
                            current = str(httpx.URL(current).join(location))
                            if (
                                allowed_hosts
                                and _allowlist_key(current) not in allowed_hosts
                            ):
                                raise FetchError(
                                    "Metadata redirect нарушает domain allowlist"
                                )
                            continue
                        if response.status_code in {404, 410}:
                            return MetadataResponse(
                                status_code=response.status_code,
                                final_url=str(response.url),
                                text="",
                                media_type="",
                            )
                        if response.status_code >= 400:
                            raise FetchError(
                                f"Metadata вернул HTTP {response.status_code}"
                            )
                        content_type = response.headers.get("content-type", "")
                        media_type = content_type.split(";", 1)[0].lower()
                        if media_type not in ALLOWED_METADATA_TYPES:
                            raise FetchError(
                                "Metadata имеет запрещённый content type"
                            )
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise FetchError(
                                    "Metadata превышает допустимый размер"
                                )
                            chunks.append(chunk)
                        content = b"".join(chunks)
                        text, _, _ = decode_html_bytes(content, content_type)
                        return MetadataResponse(
                            status_code=response.status_code,
                            final_url=str(response.url),
                            text=text,
                            media_type=media_type,
                        )
                except httpx.TimeoutException as exc:
                    raise FetchError("Истекло время загрузки metadata") from exc
                except httpx.HTTPError as exc:
                    raise FetchError("Ошибка загрузки metadata") from exc
        raise FetchError("Слишком много перенаправлений metadata")


def origin(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    return f"{parsed.scheme.lower()}://{netloc}"
