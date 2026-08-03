from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import re
from typing import Iterable

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    document_id: str
    evidence_id: str
    locator: str
    text: str
    identity_match: bool
    source_authority: int
    observed_at: datetime
    mandatory_questions: frozenset[str] = frozenset()

    @property
    def digest(self) -> str:
        payload = "\x1f".join(
            (self.document_id, self.evidence_id, self.locator, self.text)
        ).encode("utf-8")
        return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    document_id: str
    evidence_id: str
    locator: str
    digest: str
    score: int
    text: str


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_RE.findall(value))


def rank_evidence_chunks(
    query: str,
    chunks: Iterable[EvidenceChunk],
    *,
    mandatory_question: str | None = None,
    now: datetime | None = None,
    limit: int = 20,
) -> list[RetrievalResult]:
    """Return deterministic, source-preserving lexical retrieval results.

    This is the in-process SR-08 baseline. It deliberately avoids a vector
    dependency while preserving document/evidence traceability and applying
    explicit ranking penalties for identity mismatch and stale evidence.
    """
    if limit < 1:
        raise ValueError("limit must be positive")

    query_tokens = _tokens(query)
    reference_time = now or datetime.now(UTC)
    if reference_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    ranked: list[RetrievalResult] = []
    for chunk in chunks:
        observed_at = chunk.observed_at
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")

        overlap = len(query_tokens & _tokens(chunk.text))
        age_days = max(0, (reference_time - observed_at).days)
        freshness = max(0, 365 - age_days)
        identity = 1_000 if chunk.identity_match else -1_000
        authority = max(0, min(100, chunk.source_authority)) * 10
        mandatory = (
            500
            if mandatory_question
            and mandatory_question in chunk.mandatory_questions
            else 0
        )
        score = overlap * 100 + identity + authority + freshness + mandatory

        ranked.append(
            RetrievalResult(
                document_id=chunk.document_id,
                evidence_id=chunk.evidence_id,
                locator=chunk.locator,
                digest=chunk.digest,
                score=score,
                text=chunk.text,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            item.document_id,
            item.evidence_id,
            item.locator,
            item.digest,
        )
    )
    return ranked[:limit]
