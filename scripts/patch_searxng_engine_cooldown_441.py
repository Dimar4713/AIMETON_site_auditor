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
    "app/search_gateway/providers.py",
    "import hashlib\nimport html\nimport xml.etree.ElementTree as ET\nfrom abc import ABC, abstractmethod\n",
    "import hashlib\nimport html\nimport time\nimport xml.etree.ElementTree as ET\nfrom abc import ABC, abstractmethod\nfrom collections.abc import Callable\n",
)

replace_once(
    "app/search_gateway/providers.py",
    '''        engines: tuple[str, ...] = (),\n        engine_fanout: int | None = None,\n        transport: httpx.AsyncBaseTransport | None = None,\n    ) -> None:\n        super().__init__(transport=transport)\n        self._base_url = (base_url or "").strip().rstrip("/")\n        self._engines = tuple(item.strip() for item in engines if item.strip())\n        self._engine_fanout = max(1, int(engine_fanout)) if engine_fanout is not None else None\n        self._degradations: dict[int, ProviderDegradation] = {}\n''',
    '''        engines: tuple[str, ...] = (),\n        engine_fanout: int | None = None,\n        engine_rate_limit_cooldown_seconds: float = 3600.0,\n        engine_block_cooldown_seconds: float = 86400.0,\n        engine_error_cooldown_seconds: float = 60.0,\n        clock: Callable[[], float] = time.monotonic,\n        transport: httpx.AsyncBaseTransport | None = None,\n    ) -> None:\n        super().__init__(transport=transport)\n        self._base_url = (base_url or "").strip().rstrip("/")\n        self._engines = tuple(item.strip() for item in engines if item.strip())\n        self._engine_fanout = max(1, int(engine_fanout)) if engine_fanout is not None else None\n        self._engine_rate_limit_cooldown_seconds = max(0.0, float(engine_rate_limit_cooldown_seconds))\n        self._engine_block_cooldown_seconds = max(0.0, float(engine_block_cooldown_seconds))\n        self._engine_error_cooldown_seconds = max(0.0, float(engine_error_cooldown_seconds))\n        self._clock = clock\n        self._engine_cooldown_until: dict[str, float] = {}\n        self._degradations: dict[int, ProviderDegradation] = {}\n''',
)

replace_once(
    "app/search_gateway/providers.py",
    '''    def _engines_for_request(self, request: SearchRequest) -> tuple[str, ...]:\n        if not self._engines:\n            return ()\n        if self._engine_fanout is None or self._engine_fanout >= len(self._engines):\n            return self._engines\n        seed = "\\n".join((" ".join(request.query.split()).casefold(), request.language.casefold()))\n        digest = hashlib.sha256(seed.encode("utf-8")).digest()\n        start = int.from_bytes(digest[:8], "big") % len(self._engines)\n        return tuple(\n            self._engines[(start + offset) % len(self._engines)]\n            for offset in range(self._engine_fanout)\n        )\n\n    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n''',
    '''    def _engines_for_request(self, request: SearchRequest) -> tuple[str, ...]:\n        if not self._engines:\n            return ()\n        now = self._clock()\n        eligible = tuple(\n            engine\n            for engine in self._engines\n            if self._engine_cooldown_until.get(engine.casefold(), 0.0) <= now\n        )\n        if not eligible:\n            return ()\n        if self._engine_fanout is None or self._engine_fanout >= len(eligible):\n            return eligible\n        seed = "\\n".join((" ".join(request.query.split()).casefold(), request.language.casefold()))\n        digest = hashlib.sha256(seed.encode("utf-8")).digest()\n        start = int.from_bytes(digest[:8], "big") % len(eligible)\n        return tuple(\n            eligible[(start + offset) % len(eligible)]\n            for offset in range(self._engine_fanout)\n        )\n\n    def _cooldown_seconds(self, reason: FallbackReason) -> float:\n        if reason is FallbackReason.RATE_LIMITED:\n            return self._engine_rate_limit_cooldown_seconds\n        if reason in {FallbackReason.CAPTCHA, FallbackReason.PROVIDER_BLOCKED}:\n            return self._engine_block_cooldown_seconds\n        return self._engine_error_cooldown_seconds\n\n    def _record_degradation(self, degradation: ProviderDegradation) -> None:\n        cooldown = self._cooldown_seconds(degradation.reason)\n        if cooldown <= 0:\n            return\n        configured = {engine.casefold(): engine for engine in self._engines}\n        blocked_until = self._clock() + cooldown\n        for upstream in degradation.upstreams:\n            canonical = configured.get(upstream.casefold())\n            if canonical is None:\n                continue\n            key = canonical.casefold()\n            self._engine_cooldown_until[key] = max(\n                self._engine_cooldown_until.get(key, 0.0),\n                blocked_until,\n            )\n\n    def consume_degradation(self, request: SearchRequest) -> ProviderDegradation | None:\n''',
)

replace_once(
    "app/search_gateway/providers.py",
    '''        selected_engines = self._engines_for_request(request)\n        if selected_engines:\n            params["engines"] = ",".join(selected_engines)\n\n        payload = await self._request_json(\n''',
    '''        selected_engines = self._engines_for_request(request)\n        if self._engines and not selected_engines:\n            raise ProviderError(\n                "searxng upstream engines cooling down",\n                retryable=False,\n                reason=FallbackReason.CIRCUIT_OPEN,\n            )\n        if selected_engines:\n            params["engines"] = ",".join(selected_engines)\n\n        payload = await self._request_json(\n''',
)

replace_once(
    "app/search_gateway/providers.py",
    '''        degradation = self._classify_unresponsive(payload.get("unresponsive_engines") or [])\n        if degradation is not None:\n            if results:\n''',
    '''        degradation = self._classify_unresponsive(payload.get("unresponsive_engines") or [])\n        if degradation is not None:\n            self._record_degradation(degradation)\n            if results:\n''',
)

replace_once(
    "app/search_gateway/factory.py",
    '''            engine_fanout=_int_env(\n                "SEARXNG_ENGINES_PER_REQUEST", 2, minimum=1, maximum=64\n            ),\n        ),\n''',
    '''            engine_fanout=_int_env(\n                "SEARXNG_ENGINES_PER_REQUEST", 2, minimum=1, maximum=64\n            ),\n            engine_rate_limit_cooldown_seconds=_float_env(\n                "SEARXNG_ENGINE_RATE_LIMIT_COOLDOWN_SECONDS",\n                3600.0,\n                minimum=0.0,\n                maximum=604800.0,\n            ),\n            engine_block_cooldown_seconds=_float_env(\n                "SEARXNG_ENGINE_BLOCK_COOLDOWN_SECONDS",\n                86400.0,\n                minimum=0.0,\n                maximum=2592000.0,\n            ),\n            engine_error_cooldown_seconds=_float_env(\n                "SEARXNG_ENGINE_ERROR_COOLDOWN_SECONDS",\n                60.0,\n                minimum=0.0,\n                maximum=86400.0,\n            ),\n        ),\n''',
)

replace_once(
    ".env.example",
    "SEARXNG_ENGINES_PER_REQUEST=2\n",
    "SEARXNG_ENGINES_PER_REQUEST=2\nSEARXNG_ENGINE_RATE_LIMIT_COOLDOWN_SECONDS=3600\nSEARXNG_ENGINE_BLOCK_COOLDOWN_SECONDS=86400\nSEARXNG_ENGINE_ERROR_COOLDOWN_SECONDS=60\n",
)
