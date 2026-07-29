from __future__ import annotations

from app.document_pipeline import get_document_pipeline
from app.evidence_crawler.service import BootstrapEvidenceCrawler


_crawler: BootstrapEvidenceCrawler | None = None


def get_evidence_crawler() -> BootstrapEvidenceCrawler:
    global _crawler
    if _crawler is None:
        _crawler = BootstrapEvidenceCrawler(
            document_pipeline=get_document_pipeline(),
        )
    return _crawler


def reset_evidence_crawler() -> None:
    global _crawler
    _crawler = None
