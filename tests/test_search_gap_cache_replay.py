import pytest

from app.search_gap_cache_replay import replay_sparse_gap_from_cache, search_cache_key
from app.search_gateway.models import SearchItem, SearchPolicy, SearchRequest


class FakeCache:
    def __init__(self, values):
        self.values = values
        self.get_calls = 0

    async def get(self, key):
        self.get_calls += 1
        return self.values.get(key)

    async def set(self, key, results, ttl_seconds):
        raise AssertionError("cache replay must be read-only")


def request(query="dentistry Krasnoyarsk contacts"):
    return SearchRequest(
        query=query,
        limit=10,
        mission_id="m1",
        correlation_id="c1",
    )


def item(url):
    return SearchItem(url=url, title="x", snippet="x", provider="searxng")


@pytest.mark.asyncio
async def test_cache_replay_uses_exact_cached_key_without_provider_path():
    req = request()
    policy = SearchPolicy()
    cache = FakeCache({search_cache_key(req, policy): [
        item("https://known.example/a"),
        item("https://new.example/a"),
    ]})

    result = await replay_sparse_gap_from_cache(
        cache=cache,
        request=req,
        policy=policy,
        suggested_follow_up_query="  DENTISTRY   Krasnoyarsk contacts ",
        baseline_domains=["known.example"],
        mission_id="m1",
        attempt_id="a1",
        effective_regime="balanced",
    )

    assert cache.get_calls == 1
    assert result.cache_hit is True
    assert result.provider_calls == 0
    assert result.retained_outcome is not None
    assert result.retained_outcome.evidence.added_unique_domains == 1
    assert result.retained_outcome.assess().verdict == "supported"


@pytest.mark.asyncio
async def test_cache_miss_is_explicit_and_does_not_fabricate_evidence():
    req = request()
    result = await replay_sparse_gap_from_cache(
        cache=FakeCache({}),
        request=req,
        policy=SearchPolicy(),
        suggested_follow_up_query=req.query,
        baseline_domains=[],
        mission_id="m1",
        attempt_id="a1",
        effective_regime="discovery",
    )
    assert result.cache_hit is False
    assert result.reason_code == "search_gap_cache_miss"
    assert result.retained_outcome is None
    assert result.provider_calls == 0


@pytest.mark.asyncio
async def test_cache_replay_rejects_query_identity_mismatch():
    with pytest.raises(ValueError, match="search_gap_cache_replay_query_mismatch"):
        await replay_sparse_gap_from_cache(
            cache=FakeCache({}),
            request=request(),
            policy=SearchPolicy(),
            suggested_follow_up_query="different query",
            baseline_domains=[],
            mission_id="m1",
            attempt_id="a1",
            effective_regime="balanced",
        )
