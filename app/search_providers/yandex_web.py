from __future__ import annotations

import base64
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

YANDEX_WEB_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/search"


class YandexModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class YandexSearchRecord(YandexModel):
    id: str
    provider: str = "yandex_web_search"
    source_kind: str = "search_engine"
    accessed_at: datetime
    query: str
    rank: int = Field(ge=1)
    title: str
    url: AnyHttpUrl
    host: str
    snippet: str = ""
    response_digest: str
    lifecycle_state: str = "evidence"
    authority_verified: bool = False


class YandexSearchResult(YandexModel):
    schema_version: str = "0.1.0"
    provider: str = "yandex_web_search"
    state: str
    query: str
    records: list[YandexSearchRecord] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    authority_verified: bool = False


class YandexSearchHealth(YandexModel):
    provider: str = "yandex_web_search"
    state: str
    api_key_configured: bool
    folder_id_configured: bool
    search_type: str
    family_mode: str
    results_per_page: int
    endpoint: AnyHttpUrl = YANDEX_WEB_SEARCH_URL
    secrets_exposed: bool = False


def _digest(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    return "" if found is None else "".join(found.itertext()).strip()


def _wire_enum(value: str, prefix: str) -> str:
    value = value.strip()
    if value.startswith(prefix):
        value = value.removeprefix(prefix)
    return value.lower()


def _short_upstream_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = " ".join(response.text.split())[:240]
        return f"status_{response.status_code}:{text}" if text else f"status_{response.status_code}"
    if isinstance(payload, dict):
        code = payload.get("code")
        message = payload.get("message") or payload.get("error") or payload.get("details")
        parts = [str(item) for item in (code, message) if item not in (None, "")]
        if parts:
            return f"status_{response.status_code}:{':'.join(parts)[:500]}"
    return f"status_{response.status_code}"


class YandexWebSearchProvider:
    def __init__(self, *, api_key: str | None = None, folder_id: str | None = None, client: httpx.Client | None = None) -> None:
        self._api_key = (api_key or os.getenv("YANDEX_SEARCH_API_KEY", "")).strip()
        self._folder_id = (folder_id or os.getenv("YANDEX_CLOUD_FOLDER_ID", "")).strip()
        self._search_type = os.getenv("YANDEX_SEARCH_TYPE", "SEARCH_TYPE_RU").strip()
        self._family_mode = os.getenv("YANDEX_SEARCH_FAMILY_MODE", "FAMILY_MODE_MODERATE").strip()
        self._results_per_page = int(os.getenv("YANDEX_SEARCH_RESULTS_PER_PAGE", "10"))
        self._client = client

    def health(self) -> YandexSearchHealth:
        configured = bool(self._api_key and self._folder_id)
        return YandexSearchHealth(
            state="active" if configured else "not_configured",
            api_key_configured=bool(self._api_key),
            folder_id_configured=bool(self._folder_id),
            search_type=self._search_type,
            family_mode=self._family_mode,
            results_per_page=self._results_per_page,
        )

    def search(self, query: str, *, page: int = 0, site: str | None = None) -> YandexSearchResult:
        query = query.strip()
        if not query:
            raise ValueError("Yandex search query must not be empty")
        if len(query) > 400:
            raise ValueError("Yandex search query exceeds 400 characters")
        if not self._api_key or not self._folder_id:
            return YandexSearchResult(state="unavailable", query=query, gaps=["yandex_search_not_configured"])
        query_text = f"site:{site} {query}" if site else query
        if len(query_text) > 400:
            raise ValueError("Yandex search query with site filter exceeds 400 characters")
        payload = {
            "query": {
                "searchType": _wire_enum(self._search_type, "SEARCH_TYPE_"),
                "queryText": query_text,
                "familyMode": _wire_enum(self._family_mode, "FAMILY_MODE_"),
                "page": str(page),
                "fixTypoMode": "FIX_TYPO_MODE_ON",
            },
            "groupSpec": {
                "groupsOnPage": str(self._results_per_page),
            },
            "region": "225",
            "l10N": "ru",
            "folderId": self._folder_id,
            "responseFormat": "FORMAT_XML",
        }
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.post(
                YANDEX_WEB_SEARCH_URL,
                headers={"Authorization": f"Api-Key {self._api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if response.is_error:
                raise RuntimeError(f"yandex_web_search_upstream_{_short_upstream_error(response)}")
            envelope: dict[str, Any] = response.json()
            xml_bytes = base64.b64decode(envelope["rawData"])
            root = ET.fromstring(xml_bytes)
        except RuntimeError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, ET.ParseError) as exc:
            raise RuntimeError("yandex_web_search_request_failed") from exc
        finally:
            if owns_client:
                client.close()

        records: list[YandexSearchRecord] = []
        for rank, doc in enumerate(root.findall(".//doc"), start=1):
            url = _text(doc, "url")
            title = _text(doc, "title") or url
            if not url:
                continue
            passages = ["".join(item.itertext()).strip() for item in doc.findall(".//passage")]
            raw = {"url": url, "title": title, "passages": passages, "rank": rank}
            records.append(YandexSearchRecord(
                id=f"yandex_result_{_digest(raw).removeprefix('sha256:')[:24]}",
                accessed_at=datetime.now(UTC), query=query, rank=rank, title=title,
                url=url, host=urlparse(url).netloc, snippet=" ".join(filter(None, passages)),
                response_digest=_digest(raw),
            ))
        return YandexSearchResult(state="resolved" if records else "unresolved", query=query, records=records)


_provider: YandexWebSearchProvider | None = None


def get_yandex_web_search_provider() -> YandexWebSearchProvider:
    global _provider
    if _provider is None:
        _provider = YandexWebSearchProvider()
    return _provider
