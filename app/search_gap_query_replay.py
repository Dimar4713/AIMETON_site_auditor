from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from app.search_gap_hindsight import GapHindsightEvidence
from app.search_gap_retained_evidence import RetainedGapOutcome
from app.search_gap_shadow_refinement import GapCode
from app.search_regime_utility import SearchRegime


def _canonical_query(value: str) -> str:
    return " ".join(value.split()).strip().casefold()


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


class ReplaySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    qualified: bool = False
    direct_or_official: bool = False
    excluded: bool = False
    region_confirmed: bool = False
    industry_confirmed: bool = False
    novel_entity: bool | None = None
    rare_hit: bool | None = None


class GapQueryReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str = Field(min_length=1, max_length=120)
    attempt_id: str = Field(min_length=1, max_length=120)
    gap_code: GapCode
    effective_regime: SearchRegime
    suggested_follow_up_query: str = Field(min_length=1, max_length=500)
    observed_query: str = Field(min_length=1, max_length=500)
    baseline_domains: list[str] = Field(default_factory=list)
    results: list[ReplaySearchResult] = Field(default_factory=list)
    routing_changed: bool = False

    def to_retained_outcome(self) -> RetainedGapOutcome:
        if self.routing_changed:
            raise ValueError("gap_query_replay_requires_routing_unchanged")
        if _canonical_query(self.suggested_follow_up_query) != _canonical_query(self.observed_query):
            raise ValueError("gap_query_replay_query_mismatch")

        baseline = {item.casefold().removeprefix("www.") for item in self.baseline_domains if item}
        result_domains = [_domain(item.url) for item in self.results if _domain(item.url)]
        new_domains = {domain for domain in result_domains if domain not in baseline}
        excluded = sum(item.excluded for item in self.results)
        duplicates = max(0, len(result_domains) - len(set(result_domains)))
        qualified = sum(item.qualified and not item.excluded for item in self.results)
        direct = sum(item.direct_or_official and not item.excluded for item in self.results)
        region = sum(item.region_confirmed and not item.excluded for item in self.results)
        industry = sum(item.industry_confirmed and not item.excluded for item in self.results)

        novelty_labels = [item.novel_entity for item in self.results if item.novel_entity is not None]
        rare_labels = [item.rare_hit for item in self.results if item.rare_hit is not None]
        novel_entities = sum(bool(value) for value in novelty_labels) if novelty_labels else None
        rare_hits = sum(bool(value) for value in rare_labels) if rare_labels else None

        evidence = GapHindsightEvidence(
            added_raw_results=len(self.results),
            added_unique_domains=len(new_domains),
            added_qualified_candidates=qualified,
            added_direct_or_official_candidates=direct,
            duplicate_results=duplicates,
            excluded_results=excluded,
            region_confirmed_candidates=region,
            industry_confirmed_candidates=industry,
            novel_entities=novel_entities,
            rare_hits=rare_hits,
        )
        return RetainedGapOutcome(
            mission_id=self.mission_id,
            attempt_id=self.attempt_id,
            follow_up_query=self.observed_query,
            gap_code=self.gap_code,
            effective_regime=self.effective_regime,
            evidence=evidence,
            routing_changed=False,
        )
