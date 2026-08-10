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
    '''class ProviderHealth(GatewayModel):\n    provider: str\n    state: ProviderReadiness\n    ready: bool\n    configured: bool\n    paid: bool\n    circuit_state: Literal["closed", "open", "half_open"]\n    quota_remaining: int | None = Field(default=None, ge=0)\n''',
    '''class UpstreamCooldown(GatewayModel):\n    upstream: str = Field(min_length=1, max_length=100)\n    reason: FallbackReason\n    retry_after_seconds: int = Field(ge=0, le=2592000)\n\n\nclass ProviderHealth(GatewayModel):\n    provider: str\n    state: ProviderReadiness\n    ready: bool\n    configured: bool\n    paid: bool\n    circuit_state: Literal["closed", "open", "half_open"]\n    quota_remaining: int | None = Field(default=None, ge=0)\n    upstream_cooldowns: list[UpstreamCooldown] | None = None\n''',
)

replace_once(
    "app/search_gateway/providers.py",
    '''from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest\n''',
    '''from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest, UpstreamCooldown\n''',
)
replace_once(
    "app/search_gateway/providers.py",
    '''    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n        return None\n\n    @abstractmethod\n''',
    '''    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n        return None\n\n    def upstream_cooldowns(self) -> list[UpstreamCooldown]:\n        return []\n\n    def upstream_circuit_open(self) -> bool:\n        return False\n\n    @abstractmethod\n''',
)
replace_once(
    "app/search_gateway/providers.py",
    '''        self._engine_cooldown_until: dict[str, float] = {}\n        self._degradations: dict[int, ProviderDegradation] = {}\n''',
    '''        self._engine_cooldown_until: dict[str, float] = {}\n        self._engine_cooldown_reasons: dict[str, FallbackReason] = {}\n        self._degradations: dict[int, ProviderDegradation] = {}\n''',
)
replace_once(
    "app/search_gateway/providers.py",
    '''    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n        return self._degradations.pop(id(request), None)\n\n    @staticmethod\n''',
    '''    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n        return self._degradations.pop(id(request), None)\n\n    def upstream_cooldowns(self) -> list[UpstreamCooldown]:\n        now = self._clock()\n        rows: list[UpstreamCooldown] = []\n        for engine in self._engines:\n            key = engine.casefold()\n            until = self._engine_cooldown_until.get(key, 0.0)\n            if until <= now:\n                self._engine_cooldown_until.pop(key, None)\n                self._engine_cooldown_reasons.pop(key, None)\n                continue\n            remaining = max(1, int((until - now) + 0.999999))\n            rows.append(\n                UpstreamCooldown(\n                    upstream=engine,\n                    reason=self._engine_cooldown_reasons.get(\n                        key, FallbackReason.PROVIDER_ERROR\n                    ),\n                    retry_after_seconds=remaining,\n                )\n            )\n        return rows\n\n    def upstream_circuit_open(self) -> bool:\n        if not self._engines:\n            return False\n        now = self._clock()\n        return all(\n            self._engine_cooldown_until.get(engine.casefold(), 0.0) > now\n            for engine in self._engines\n        )\n\n    @staticmethod\n''',
)
replace_once(
    "app/search_gateway/providers.py",
    '''            key = canonical.casefold()\n            self._engine_cooldown_until[key] = max(\n                self._engine_cooldown_until.get(key, 0.0),\n                blocked_until,\n            )\n''',
    '''            key = canonical.casefold()\n            previous_until = self._engine_cooldown_until.get(key, 0.0)\n            if blocked_until >= previous_until:\n                self._engine_cooldown_until[key] = blocked_until\n                self._engine_cooldown_reasons[key] = degradation.reason\n''',
)

replace_once(
    "app/search_gateway/scheduler.py",
    '''from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest\n''',
    '''from app.search_gateway.models import FallbackReason, SearchItem, SearchRequest, UpstreamCooldown\n''',
)
replace_once(
    "app/search_gateway/scheduler.py",
    '''    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n        return self._provider.consume_degradation(request)\n\n    async def search(\n''',
    '''    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n        return self._provider.consume_degradation(request)\n\n    def upstream_cooldowns(self) -> list[UpstreamCooldown]:\n        return self._provider.upstream_cooldowns()\n\n    def upstream_circuit_open(self) -> bool:\n        return self._provider.upstream_circuit_open()\n\n    async def search(\n''',
)

replace_once(
    "app/search_gateway/gateway.py",
    '''        for name, provider in self._providers.items():\n            quota = self._global_quotas.get(name)\n            remaining = None if quota is None else max(0, quota - self._global_usage[name])\n            circuit_state = self._circuit_state(name)\n            maximum = policy.max_cost_by_currency.get(provider.cost_currency)\n''',
    '''        for name, provider in self._providers.items():\n            quota = self._global_quotas.get(name)\n            remaining = None if quota is None else max(0, quota - self._global_usage[name])\n            upstream_cooldowns = provider.upstream_cooldowns()\n            upstream_open = provider.upstream_circuit_open()\n            circuit_state = "open" if upstream_open else self._circuit_state(name)\n            maximum = policy.max_cost_by_currency.get(provider.cost_currency)\n''',
)
replace_once(
    "app/search_gateway/gateway.py",
    '''                    circuit_state=circuit_state,\n                    quota_remaining=remaining,\n                )\n''',
    '''                    circuit_state=circuit_state,\n                    quota_remaining=remaining,\n                    upstream_cooldowns=upstream_cooldowns or None,\n                )\n''',
)

replace_once(
    "app/main.py",
    '''        item.model_dump(mode="json")\n        for item in get_search_gateway().health(search_policy_from_env())\n''',
    '''        item.model_dump(mode="json", exclude_none=True)\n        for item in get_search_gateway().health(search_policy_from_env())\n''',
)
