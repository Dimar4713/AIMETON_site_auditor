from __future__ import annotations

from app.document_pipeline import get_document_pipeline
from app.entity_resolution import get_entity_resolver
from app.identity_evidence.service import IdentityEvidenceService
from app.search_gateway import get_search_gateway


_service: IdentityEvidenceService | None = None


def get_identity_evidence_service() -> IdentityEvidenceService:
    global _service
    if _service is None:
        _service = IdentityEvidenceService(
            search_gateway=get_search_gateway(),
            document_pipeline=get_document_pipeline(),
            entity_resolver=get_entity_resolver(),
        )
    return _service


def reset_identity_evidence_service() -> None:
    global _service
    _service = None
