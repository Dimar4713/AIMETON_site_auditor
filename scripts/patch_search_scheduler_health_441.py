from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/search_gateway/models.py",
    '''class ProviderHealth(GatewayModel):\n    provider: str\n    state: ProviderReadiness\n    ready: bool\n    configured: bool\n    paid: bool\n    circuit_state: Literal["closed", "open", "half_open"]\n    quota_remaining: int | None = Field(default=None, ge=0)\n    upstream_cooldowns: list[UpstreamCooldown] | None = None\n''',
    '''class ProviderScheduling(GatewayModel):\n    max_concurrency: int = Field(ge=1, le=64)\n    jitter_min_seconds: float = Field(ge=0.0, le=30.0)\n    jitter_max_seconds: float = Field(ge=0.0, le=30.0)\n\n\nclass ProviderHealth(GatewayModel):\n    provider: str\n    state: ProviderReadiness\n    ready: bool\n    configured: bool\n    paid: bool\n    circuit_state: Literal["closed", "open", "half_open"]\n    quota_remaining: int | None = Field(default=None, ge=0)\n    upstream_cooldowns: list[UpstreamCooldown] | None = None\n    scheduling: ProviderScheduling | None = None\n''',
)

replace_once(
    "app/search_gateway/providers.py",
    '''from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest, UpstreamCooldown\n''',
    '''from app.search_gateway.models import (\n    FallbackReason,\n    ProviderScheduling,\n    SearchItem,\n    SearchRequest,\n    UpstreamCooldown,\n)\n''',
)
replace_once(
    "app/search_gateway/providers.py",
    '''    def upstream_circuit_open(self) -> bool:\n        return False\n\n    @abstractmethod\n''',
    '''    def upstream_circuit_open(self) -> bool:\n        return False\n\n    def scheduling_policy(self) -> ProviderScheduling | None:\n        return None\n\n    @abstractmethod\n''',
)

replace_once(
    "app/search_gateway/scheduler.py",
    '''from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest, UpstreamCooldown\n''',
    '''from app.search_gateway.models import (\n    FallbackReason,\n    ProviderScheduling,\n    SearchItem,\n    SearchRequest,\n    UpstreamCooldown,\n)\n''',
)
replace_once(
    "app/search_gateway/scheduler.py",
    '''    def upstream_circuit_open(self) -> bool:\n        return self._provider.upstream_circuit_open()\n\n    async def search(\n''',
    '''    def upstream_circuit_open(self) -> bool:\n        return self._provider.upstream_circuit_open()\n\n    def scheduling_policy(self) -> ProviderScheduling:\n        return ProviderScheduling(\n            max_concurrency=self.max_concurrency,\n            jitter_min_seconds=self._jitter_min_seconds,\n            jitter_max_seconds=self._jitter_max_seconds,\n        )\n\n    async def search(\n''',
)

replace_once(
    "app/search_gateway/gateway.py",
    '''                    quota_remaining=remaining,\n                    upstream_cooldowns=upstream_cooldowns or None,\n                )\n''',
    '''                    quota_remaining=remaining,\n                    upstream_cooldowns=upstream_cooldowns or None,\n                    scheduling=provider.scheduling_policy(),\n                )\n''',
)
