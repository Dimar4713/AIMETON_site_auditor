from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from app.search_observer import SearchWaveTelemetry
from app.search_observer_llm import SearchObserverRecommendation
from app.search_observer_models import ResolvedObserverModel


class ArenaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArenaCase(ArenaModel):
    case_id: str = Field(min_length=1, max_length=120)
    telemetry: SearchWaveTelemetry


class ArenaResult(ArenaModel):
    case_id: str
    profile_name: str
    provider: str
    model: str
    configured: bool
    latency_ms: int = Field(ge=0)
    schema_valid: bool
    routing_changed: bool = False
    recommendation_count: int = Field(ge=0)
    sufficient_evidence: bool | None = None
    actions: dict[str, int] = Field(default_factory=dict)
    error_code: str | None = None


Evaluator = Callable[[SearchWaveTelemetry, ResolvedObserverModel], Awaitable[SearchObserverRecommendation | None]]


def validate_replay_case(case: ArenaCase) -> None:
    """Require replay-complete observer telemetry; compact trace previews are insufficient."""
    telemetry = case.telemetry
    if telemetry.query_count <= 0:
        raise ValueError("arena_case_has_no_queries")
    if len(telemetry.directions) != telemetry.query_count:
        raise ValueError("arena_case_direction_count_mismatch")
    if any(not item.query.strip() for item in telemetry.directions):
        raise ValueError("arena_case_missing_query_text")


async def evaluate_case(
    case: ArenaCase,
    model: ResolvedObserverModel,
    evaluator: Evaluator,
) -> ArenaResult:
    validate_replay_case(case)
    if not model.configured:
        return ArenaResult(
            case_id=case.case_id,
            profile_name=model.profile_name,
            provider=model.provider.value,
            model=model.model,
            configured=False,
            latency_ms=0,
            schema_valid=False,
            error_code="model_not_configured",
        )

    started = time.perf_counter()
    recommendation = await evaluator(case.telemetry, model)
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    if recommendation is None:
        return ArenaResult(
            case_id=case.case_id,
            profile_name=model.profile_name,
            provider=model.provider.value,
            model=model.model,
            configured=True,
            latency_ms=latency_ms,
            schema_valid=False,
            error_code="observer_evaluation_failed",
        )

    actions: dict[str, int] = {}
    for item in recommendation.recommendations:
        actions[item.action.value] = actions.get(item.action.value, 0) + 1

    return ArenaResult(
        case_id=case.case_id,
        profile_name=model.profile_name,
        provider=model.provider.value,
        model=model.model,
        configured=True,
        latency_ms=latency_ms,
        schema_valid=True,
        routing_changed=recommendation.routing_changed,
        recommendation_count=len(recommendation.recommendations),
        sufficient_evidence=recommendation.sufficient_evidence,
        actions=actions,
    )


def summarize_arena(results: list[ArenaResult]) -> list[dict[str, object]]:
    grouped: dict[str, list[ArenaResult]] = {}
    for item in results:
        grouped.setdefault(item.profile_name, []).append(item)

    summary: list[dict[str, object]] = []
    for profile_name, items in sorted(grouped.items()):
        configured = [item for item in items if item.configured]
        valid = [item for item in configured if item.schema_valid]
        latencies = [item.latency_ms for item in valid]
        summary.append(
            {
                "profile_name": profile_name,
                "case_count": len(items),
                "configured_count": len(configured),
                "schema_valid_count": len(valid),
                "schema_valid_rate": round(len(valid) / len(configured), 6) if configured else 0.0,
                "mean_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
                "routing_changed_count": sum(item.routing_changed for item in items),
            }
        )
    return summary
