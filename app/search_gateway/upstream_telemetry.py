from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.search_gateway.models import (
    FallbackReason,
    GatewayModel,
    ProviderHealth,
    SearchPolicy,
    SearchRequest,
)
from app.search_gateway.providers import (
    ProviderDegradation,
    SearxngProvider as BaseSearxngProvider,
)
from app.search_gateway.scheduler import ScheduledProvider as BaseScheduledProvider
from app.search_gateway.traced_gateway import TracedSearchGateway as BaseTracedSearchGateway


class UpstreamTelemetry(GatewayModel):
    upstream: str = Field(min_length=1, max_length=100)
    selected_requests: int = Field(ge=0)
    degradation_events: int = Field(ge=0)
    degradation_rate: float = Field(ge=0.0, le=1.0)
    last_degradation_reason: FallbackReason | None = None
    scope: Literal["process_lifetime"] = "process_lifetime"


class TelemetryProviderHealth(ProviderHealth):
    upstream_telemetry: list[UpstreamTelemetry] | None = None


class SearxngProvider(BaseSearxngProvider):
    """SearXNG provider with zero-routing-change, process-lifetime engine telemetry."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._engine_selected_requests: dict[str, int] = {}
        self._engine_degradation_events: dict[str, int] = {}
        self._engine_last_degradation_reason: dict[str, FallbackReason] = {}

    def _engines_for_request(self, request: SearchRequest) -> tuple[str, ...]:
        selected = super()._engines_for_request(request)
        for engine in selected:
            key = engine.casefold()
            self._engine_selected_requests[key] = self._engine_selected_requests.get(key, 0) + 1
        return selected

    def _record_degradation(self, degradation: ProviderDegradation) -> None:
        configured = {engine.casefold(): engine for engine in self._engines}
        seen: set[str] = set()
        for upstream in degradation.upstreams:
            canonical = configured.get(upstream.casefold())
            if canonical is None:
                continue
            key = canonical.casefold()
            if key in seen:
                continue
            seen.add(key)
            self._engine_degradation_events[key] = self._engine_degradation_events.get(key, 0) + 1
            self._engine_last_degradation_reason[key] = degradation.reason
        super()._record_degradation(degradation)

    def upstream_telemetry(self) -> list[UpstreamTelemetry]:
        rows: list[UpstreamTelemetry] = []
        for engine in self._engines:
            key = engine.casefold()
            selected = self._engine_selected_requests.get(key, 0)
            degraded = self._engine_degradation_events.get(key, 0)
            if selected == 0 and degraded == 0:
                continue
            rate = 0.0 if selected <= 0 else min(1.0, degraded / selected)
            rows.append(
                UpstreamTelemetry(
                    upstream=engine,
                    selected_requests=selected,
                    degradation_events=degraded,
                    degradation_rate=rate,
                    last_degradation_reason=self._engine_last_degradation_reason.get(key),
                )
            )
        return rows


class ScheduledProvider(BaseScheduledProvider):
    def upstream_telemetry(self) -> list[UpstreamTelemetry]:
        getter = getattr(self._provider, "upstream_telemetry", None)
        return getter() if callable(getter) else []


class TracedSearchGateway(BaseTracedSearchGateway):
    def health(self, policy: SearchPolicy | None = None) -> list[ProviderHealth]:
        rows = super().health(policy)
        enriched: list[ProviderHealth] = []
        for row in rows:
            provider = self._providers[row.provider]
            getter = getattr(provider, "upstream_telemetry", None)
            telemetry = getter() if callable(getter) else []
            if telemetry:
                enriched.append(
                    TelemetryProviderHealth(
                        **row.model_dump(),
                        upstream_telemetry=telemetry,
                    )
                )
            else:
                enriched.append(row)
        return enriched
