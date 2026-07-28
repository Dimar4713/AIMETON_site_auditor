from __future__ import annotations

import os

from app.document_pipeline.fetchers import Crawl4AIHttpWorker
from app.document_pipeline.pipeline import DocumentPipeline


_pipeline: DocumentPipeline | None = None


def get_document_pipeline() -> DocumentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentPipeline(
            crawl4ai=Crawl4AIHttpWorker(
                os.getenv("CRAWL4AI_BASE_URL"),
                api_token=os.getenv("CRAWL4AI_API_TOKEN"),
            ),
            max_concurrency=2,
        )
    return _pipeline
