from __future__ import annotations

from collections import Counter
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer_llm import SearchObserverRecommendation
from app.search_observer_models import ResolvedObserverModel


class ArenaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelArenaObservation(ArenaModel):
    scenario_slug: str = Field(min_length=1, max_length=120)
    profile_name: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=160)
    tier: str = Field(pattern=r"^O[12]$")
    latency_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    schema_valid: bool
    routing_changed: bool = False
    sufficient_evidence: bool | None = None
    recommendation_count: int = Field(default=0, ge=0)
    action_counts: dict[str, int] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=120)


class ModelArenaSummary(ArenaModel):
    profile_name: str
    provider: str
    model: str
    scenario_count: int = Field(ge=0)
    schema_success_rate: float = Field(ge=0.0, le=1.0)
    routing_violation_count: int = Field(ge=0)
    mean_latency_ms: float = Field(ge=0.0)
    total_estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    action_counts: dict[str, int] = Field(default_factory=dict)


def observation_from_recommendation(
    *,
    scenario_slug: str,
    model: ResolvedObserverModel,
    latency_ms: int,
    recommendation: SearchObserverRecommendation | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    error_code: str | None = None,
) -> ModelArenaObservation:
    actions: Counter[str] = Counter()
    if recommendation is not None:
        actions.update(item.action.value for item in recommendation.recommendations)
    return ModelArenaObservation(
        scenario_slug=scenario_slug,
        profile_name=model.profile_name,
        provider=model.provider.value,
        model=model.model,
        tier=model.tier,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        schema_valid=recommendation is not None,
        routing_changed=False if recommendation is None else recommendation.routing_changed,
        sufficient_evidence=None if recommendation is None else recommendation.sufficient_evidence,
        recommendation_count=0 if recommendation is None else len(recommendation.recommendations),
        action_counts=dict(actions),
        error_code=error_code,
    )


def summarize_model_arena(observations: list[ModelArenaObservation]) -> list[ModelArenaSummary]:
    grouped: dict[str, list[ModelArenaObservation]] = {}
    for item in observations:
        grouped.setdefault(item.profile_name, []).append(item)

    summaries: list[ModelArenaSummary] = []
    for profile_name, items in grouped.items():
        action_counts: Counter[str] = Counter()
        for item in items:
            action_counts.update(item.action_counts)
        costs = [item.estimated_cost_usd for item in items if item.estimated_cost_usd is not None]
        summaries.append(
            ModelArenaSummary(
                profile_name=profile_name,
                provider=items[0].provider,
                model=items[0].model,
                scenario_count=len(items),
                schema_success_rate=sum(1 for item in items if item.schema_valid) / len(items),
                routing_violation_count=sum(1 for item in items if item.routing_changed),
                mean_latency_ms=mean(item.latency_ms for item in items),
                total_estimated_cost_usd=sum(costs) if costs else None,
                action_counts=dict(action_counts),
            )
        )

    return sorted(
        summaries,
        key=lambda item: (
            item.routing_violation_count,
            -item.schema_success_rate,
            item.mean_latency_ms,
            float("inf") if item.total_estimated_cost_usd is None else item.total_estimated_cost_usd,
            item.profile_name,
        ),
    )
