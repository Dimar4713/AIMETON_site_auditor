from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from app.document_pipeline.cache import MemoryDocumentCache
from app.document_pipeline.extractor import Extraction, digest_text, extract_html, normalize_text
from app.document_pipeline.fetchers import (
    Crawl4AIHttpWorker,
    DynamicFetcher,
    PlaywrightFallback,
    RawDocument,
    StaticHttpFetcher,
)
from app.document_pipeline.models import (
    ContentRegion,
    DocumentDiagnostics,
    DocumentRequest,
    FetchPath,
    FetchPolicy,
    FetchedDocument,
    PromotionResult,
)
from app.sef.models import (
    DiscoveryHint,
    Document,
    DocumentFetchState,
    Evidence,
    Source,
)
from app.scraper import FetchError, normalize_url


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:32]}"


def _canonical_fetch_url(value: str) -> str:
    parsed = urlsplit(normalize_url(value))
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
    )


def _request_fingerprint(request: DocumentRequest) -> str:
    safe_shape = {
        "mission_id": request.mission_id,
        "source_id": request.source_id,
        "url_digest": _sha256(_canonical_fetch_url(str(request.url)).encode("utf-8")),
    }
    return _sha256(
        json.dumps(safe_shape, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _same_origin(left: str, right: str) -> bool:
    left_parsed = urlsplit(left)
    right_parsed = urlsplit(right)

    def effective_port(parsed) -> int | None:
        if parsed.port is not None:
            return parsed.port
        if parsed.scheme.lower() == "https":
            return 443
        if parsed.scheme.lower() == "http":
            return 80
        return None

    return (
        left_parsed.scheme.lower(),
        (left_parsed.hostname or "").lower(),
        effective_port(left_parsed),
    ) == (
        right_parsed.scheme.lower(),
        (right_parsed.hostname or "").lower(),
        effective_port(right_parsed),
    )


class DocumentPipeline:
    def __init__(
        self,
        *,
        static_fetcher: StaticHttpFetcher | None = None,
        crawl4ai: DynamicFetcher | None = None,
        browser: DynamicFetcher | None = None,
        cache: MemoryDocumentCache | None = None,
        max_concurrency: int = 2,
    ) -> None:
        self._static = static_fetcher or StaticHttpFetcher()
        self._crawl4ai = crawl4ai or Crawl4AIHttpWorker(None)
        self._browser = browser or PlaywrightFallback()
        self._cache = cache or MemoryDocumentCache()
        self._semaphore = asyncio.Semaphore(max(1, min(max_concurrency, 2)))

    async def _fallback(
        self,
        url: str,
        policy: FetchPolicy,
    ) -> RawDocument:
        if policy.allowed_hosts:
            raise FetchError(
                "Динамическое извлечение заблокировано строгой domain policy"
            )
        errors: list[FetchError] = []
        if policy.allow_crawl4ai and self._crawl4ai.configured:
            try:
                return await self._crawl4ai.fetch(
                    url,
                    timeout_seconds=policy.timeout_seconds,
                )
            except FetchError as exc:
                errors.append(exc)
        if policy.allow_browser and self._browser.configured:
            try:
                return await self._browser.fetch(
                    url,
                    timeout_seconds=policy.timeout_seconds,
                )
            except FetchError as exc:
                errors.append(exc)
        if errors:
            raise FetchError("Динамическое извлечение документа не удалось") from errors[-1]
        raise FetchError("Динамическое извлечение запрещено политикой")

    @staticmethod
    def _needs_fallback(raw: RawDocument, extraction: Extraction, policy: FetchPolicy) -> bool:
        source = raw.html.casefold()
        dynamic_markers = (
            "__next_data__",
            'id="root"',
            "id='root'",
            "enable javascript",
            "javascript is required",
        )
        return (
            len(extraction.text) < policy.min_text_length
            or any(marker in source for marker in dynamic_markers)
        )

    async def fetch(
        self,
        request: DocumentRequest,
        policy: FetchPolicy | None = None,
    ) -> FetchedDocument:
        policy = policy or FetchPolicy()
        canonical_url = _canonical_fetch_url(str(request.url))
        cache_key = _sha256(
            f"{request.mission_id}\x1f{request.source_id}\x1f{canonical_url}".encode("utf-8")
        )
        fingerprint = _request_fingerprint(request)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(
                update={
                    "diagnostics": DocumentDiagnostics(
                        request_fingerprint=fingerprint,
                        path=FetchPath.CACHE,
                        cache_hit=True,
                        fallback_used=cached.diagnostics.fallback_used,
                        raw_bytes=cached.diagnostics.raw_bytes,
                        latency_ms=0,
                        detected_encoding=cached.diagnostics.detected_encoding,
                        encoding_source=cached.diagnostics.encoding_source,
                        redirect_history=cached.diagnostics.redirect_history,
                    )
                },
                deep=True,
            )

        started = time.perf_counter()
        async with self._semaphore:
            fallback_used = False
            try:
                raw = await self._static.fetch(
                    canonical_url,
                    timeout_seconds=policy.timeout_seconds,
                    max_bytes=policy.max_bytes,
                    max_redirects=policy.max_redirects,
                    allowed_hosts=policy.allowed_hosts,
                )
                extraction = extract_html(raw.html, base_url=raw.final_url)
                fallback_used = self._needs_fallback(raw, extraction, policy)
            except FetchError as exc:
                fail_closed_markers = (
                    "локаль",
                    "служеб",
                    "размер",
                    "перенаправ",
                    "не является разрешённым",
                    "encoding_undetermined",
                    "domain allowlist",
                )
                if any(marker in str(exc).casefold() for marker in fail_closed_markers):
                    raise
                fallback_used = True
                extraction = None
            if fallback_used:
                raw = await self._fallback(canonical_url, policy)
                if len(raw.html.encode("utf-8")) > policy.max_bytes:
                    raise FetchError("Динамический документ превышает допустимый размер")
                extraction = extract_html(raw.html, base_url=raw.final_url)

        assert extraction is not None
        if len(extraction.text) < policy.min_text_length or not extraction.blocks:
            raise FetchError("В документе недостаточно извлекаемого текста")

        normalized = "\n".join(
            normalize_text(block.text) for block in extraction.blocks if block.text.strip()
        )
        raw_bytes = raw.raw_content or raw.html.encode("utf-8")
        raw_digest = _sha256(raw_bytes)
        normalized_digest = digest_text(normalized)
        accessed_at = datetime.now(UTC)
        document = Document(
            id=_stable_id(
                "doc",
                request.mission_id,
                request.source_id,
                _canonical_fetch_url(raw.final_url),
                normalized_digest,
            ),
            mission_id=request.mission_id,
            source_id=request.source_id,
            correlation_id=request.correlation_id,
            url=raw.final_url,
            title=(raw.title or extraction.title)[:1_000],
            accessed_at=accessed_at,
            fetch_status=DocumentFetchState.FETCHED,
            content_digest=normalized_digest,
            media_type=raw.media_type,
        )
        path = FetchPath(raw.path)
        result = FetchedDocument(
            document=document,
            raw_content_digest=raw_digest,
            normalized_content_digest=normalized_digest,
            normalized_text=normalized,
            blocks=extraction.blocks,
            header_blocks=[
                block
                for block in extraction.blocks
                if block.region == ContentRegion.HEADER
            ],
            footer_blocks=[
                block
                for block in extraction.blocks
                if block.region == ContentRegion.FOOTER
            ],
            links=extraction.links,
            tables=extraction.tables,
            declared_canonical_url=extraction.declared_canonical_url,
            canonical_same_origin=(
                _same_origin(raw.final_url, extraction.declared_canonical_url)
                if extraction.declared_canonical_url
                else None
            ),
            diagnostics=DocumentDiagnostics(
                request_fingerprint=fingerprint,
                path=path,
                cache_hit=False,
                fallback_used=fallback_used,
                raw_bytes=len(raw_bytes),
                latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
                detected_encoding=raw.detected_encoding,
                encoding_source=raw.encoding_source,
                redirect_history=list(raw.redirect_history),
            ),
        )
        await self._cache.set(cache_key, result, policy.cache_ttl_seconds)
        return result

    async def fetch_hint(
        self,
        hint: DiscoveryHint,
        source: Source,
        policy: FetchPolicy | None = None,
    ) -> FetchedDocument:
        if hint.mission_id != source.mission_id:
            raise ValueError("hint and source belong to different missions")
        if hint.correlation_id != source.correlation_id:
            raise ValueError("hint and source break correlation_id")
        return await self.fetch(
            DocumentRequest(
                mission_id=hint.mission_id,
                source_id=source.id,
                correlation_id=hint.correlation_id,
                url=hint.url,
            ),
            policy,
        )

    @staticmethod
    def promote_quote(
        fetched: FetchedDocument,
        *,
        locator: str,
        quote: str,
        observed_at: datetime | None = None,
    ) -> PromotionResult:
        normalized_quote = normalize_text(quote)
        block = next((item for item in fetched.blocks if item.locator == locator), None)
        if block is None:
            raise ValueError("locator is not present in the fetched document")
        if not normalized_quote or normalized_quote not in normalize_text(block.text):
            raise ValueError("quote is not present at the supplied locator")
        evidence_digest = _sha256(
            (
                f"{fetched.document.content_digest}\x1f{locator}\x1f{normalized_quote}"
            ).encode("utf-8")
        )
        promoted_at = observed_at or datetime.now(UTC)
        evidence = Evidence(
            id=_stable_id(
                "ev",
                fetched.document.id,
                locator,
                evidence_digest,
            ),
            mission_id=fetched.document.mission_id,
            source_id=fetched.document.source_id,
            document_id=fetched.document.id,
            correlation_id=fetched.document.correlation_id,
            evidence_type="document_quote",
            quote=normalized_quote,
            locator=locator,
            observed_at=promoted_at,
            digest=evidence_digest,
        )
        return PromotionResult(
            document=fetched.document,
            evidence=evidence,
            promoted_at=promoted_at,
        )
