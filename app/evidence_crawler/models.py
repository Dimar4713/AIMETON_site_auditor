from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.document_pipeline.models import FetchPath, RedirectHop
from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionOutcome,
    NextActionPlan,
)
from app.sef.models import Digest, Identifier


class CrawlerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CrawlMode(StrEnum):
    BOOTSTRAP = "bootstrap"


class CrawlStatus(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class RobotsState(StrEnum):
    ALLOWED = "allowed"
    MISSING = "missing"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class PageType(StrEnum):
    ROOT = "root"
    CONTACTS = "contacts"
    REQUISITES = "requisites"
    ABOUT = "about"
    PRODUCTS = "products"
    OTHER = "other"


class IdentitySignalKind(StrEnum):
    INN = "inn"
    OGRN = "ogrn"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    LEGAL_NAME = "legal_name"


class BootstrapCrawlPolicy(CrawlerModel):
    max_pages: int = Field(default=8, ge=1, le=20)
    max_depth: int = Field(default=2, ge=0, le=4)
    max_sitemaps: int = Field(default=3, ge=0, le=10)
    max_sitemap_urls: int = Field(default=500, ge=1, le=5_000)
    max_links_per_page: int = Field(default=40, ge=1, le=500)
    max_duration_seconds: float = Field(default=45, ge=1, le=90)
    timeout_seconds: float = Field(default=15, ge=0.1, le=60)
    metadata_max_bytes: int = Field(default=1_000_000, ge=1_024, le=5_000_000)
    min_request_interval_ms: int = Field(default=250, ge=0, le=10_000)
    allow_crawl4ai: bool = False
    allow_browser: bool = False


class CrawledPage(CrawlerModel):
    requested_url: AnyHttpUrl
    final_url: AnyHttpUrl
    depth: int = Field(ge=0)
    page_type: PageType
    document_id: Identifier
    title: str = Field(min_length=1, max_length=1_000)
    accessed_at: datetime
    media_type: str = Field(min_length=1, max_length=200)
    fetch_path: FetchPath
    raw_content_digest: Digest
    normalized_content_digest: Digest
    declared_canonical_url: AnyHttpUrl | None = None
    canonical_same_origin: bool | None = None
    redirect_history: list[RedirectHop] = Field(default_factory=list)
    link_count: int = Field(ge=0)


class IdentitySignal(CrawlerModel):
    kind: IdentitySignalKind
    value: str = Field(min_length=1, max_length=500)
    document_id: Identifier
    source_url: AnyHttpUrl
    locator: str = Field(min_length=1, max_length=1_000)
    state: str = "candidate"


class PrimaryDocumentCandidate(CrawlerModel):
    url: AnyHttpUrl
    media_type: str = Field(min_length=1, max_length=200)
    source_document_id: Identifier
    source_locator: str = Field(min_length=1, max_length=1_000)
    link_text: str = Field(default="", max_length=2_000)
    same_domain: bool
    lifecycle_state: str = "discovery_hint"


class BootstrapCrawlResult(CrawlerModel):
    schema_version: str = "0.1.0"
    mode: CrawlMode = CrawlMode.BOOTSTRAP
    status: CrawlStatus
    mission_id: Identifier
    analysis_id: Identifier
    correlation_id: Identifier
    root_url: AnyHttpUrl
    plan: NextActionPlan
    robots_state: RobotsState
    sitemap_urls: list[AnyHttpUrl] = Field(default_factory=list)
    pages: list[CrawledPage] = Field(default_factory=list)
    identity_signals: list[IdentitySignal] = Field(default_factory=list)
    primary_document_candidates: list[PrimaryDocumentCandidate] = Field(
        default_factory=list
    )
    discovered_urls: list[AnyHttpUrl] = Field(default_factory=list)
    blocked_urls: list[AnyHttpUrl] = Field(default_factory=list)
    failed_urls: list[AnyHttpUrl] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    outcome: ActionOutcome
    next_action_candidates: list[ActionCandidate] = Field(default_factory=list)
