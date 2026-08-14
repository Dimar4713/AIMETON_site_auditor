from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from app.search_gap_hindsight import GapHindsightEvidence
from app.search_gap_retained_evidence import RetainedGapOutcome
from app.search_gateway.cache import SearchCache
from app.search_gateway.gateway import policy_cache_suffix, request_fingerprint
from app.search_gateway.models import SearchPolicy, SearchRequest
from app.search_regime_utility import SearchRegime


def _canonical_query(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def _domain(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def search_cache_key(request: SearchRequest, policy: SearchPolicy) -> str:
    return f"{request_fingerprint(request)}:{policy_cache_suffix(policy)}"


class CacheReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_hit: bool
    reason_code: str
    retained_outcome: RetainedGapOutcome | None = None
    provider_calls: int = 0
    routing_changed: bool = False
    steering_enabled: bool = False


async def replay_sparse_gap_from_cache(
    *,
    cache: SearchCache,
    request: SearchRequest,
    policy: SearchPolicy,
    suggested_follow_up_query: str,
    baseline_domains: list[str],
    mission_id: str,
    attempt_id: str,
    effective_regime: SearchRegime,
) -> CacheReplayResult:
    """Replay a sparse-yield follow-up strictly from an existing cache entry.

    Cached SearchItems are enough to prove raw/domain novelty only. They do not
    contain Hunter qualification, region, industry, exclusion, or discovery
    labels, so this adapter deliberately supports only the sparse-yield gap.
    """
    if _canonical_query(suggested_follow_up_query) != _canonical_query(request.query):
        raise ValueError("search_gap_cache_replay_query_mismatch")

    cached = await cache.get(search_cache_key(request, policy))
    if cached is None:
        return CacheReplayResult(
            cache_hit=False,
            reason_code="search_gap_cache_miss",
        )

    baseline = {
        value.casefold().removeprefix("www.")
        for value in baseline_domains
        if value.strip()
    }
    domains = [_domain(str(item.url)) for item in cached]
    domains = [value for value in domains if value]
    new_domains = {value for value in domains if value not in baseline}

    retained = RetainedGapOutcome(
        mission_id=mission_id,
        attempt_id=attempt_id,
        follow_up_query=request.query,
        gap_code="sparse_yield",
        effective_regime=effective_regime,
        evidence=GapHindsightEvidence(
            added_raw_results=len(cached),
            added_unique_domains=len(new_domains),
            added_qualified_candidates=0,
            added_direct_or_official_candidates=0,
            duplicate_results=max(0, len(domains) - len(set(domains))),
            excluded_results=0,
            novel_entities=None,
            rare_hits=None,
        ),
        routing_changed=False,
    )
    return CacheReplayResult(
        cache_hit=True,
        reason_code="search_gap_cache_replay_available",
        retained_outcome=retained,
    )
