from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.sef.models import Digest, Document, Evidence, Identifier


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FetchPath(StrEnum):
    STATIC = "static"
    CRAWL4AI = "crawl4ai"
    BROWSER = "browser"
    CACHE = "cache"


class BlockKind(StrEnum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE_CELL = "table_cell"


class DocumentRequest(PipelineModel):
    mission_id: Identifier
    source_id: Identifier
    correlation_id: Identifier
    url: AnyHttpUrl


class FetchPolicy(PipelineModel):
    timeout_seconds: float = Field(default=20.0, ge=0.1, le=120)
    max_bytes: int = Field(default=1_500_000, ge=1_024, le=20_000_000)
    max_redirects: int = Field(default=8, ge=0, le=20)
    min_text_length: int = Field(default=80, ge=1, le=10_000)
    cache_ttl_seconds: int = Field(default=900, ge=0, le=86_400)
    allow_crawl4ai: bool = True
    allow_browser: bool = True


class ExtractedBlock(PipelineModel):
    locator: str = Field(min_length=1, max_length=1_000)
    kind: BlockKind
    text: str = Field(min_length=1, max_length=20_000)


class ExtractedLink(PipelineModel):
    locator: str = Field(min_length=1, max_length=1_000)
    text: str = Field(default="", max_length=2_000)
    url: AnyHttpUrl


class ExtractedTable(PipelineModel):
    locator: str = Field(min_length=1, max_length=1_000)
    rows: list[list[str]]


class DocumentDiagnostics(PipelineModel):
    request_fingerprint: Digest
    path: FetchPath
    cache_hit: bool = False
    fallback_used: bool = False
    raw_bytes: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class FetchedDocument(PipelineModel):
    document: Document
    raw_content_digest: Digest
    normalized_content_digest: Digest
    normalized_text: str = Field(min_length=1)
    blocks: list[ExtractedBlock] = Field(min_length=1)
    links: list[ExtractedLink] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    diagnostics: DocumentDiagnostics


class PromotionResult(PipelineModel):
    document: Document
    evidence: Evidence
    promoted_at: datetime
