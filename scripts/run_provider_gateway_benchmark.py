from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from app.search_gateway import (
    SearchRequest,
    get_search_gateway,
    search_policy_from_env,
)


DEFAULT_FIXTURE = Path("benchmarks/sef/provider-gateway-5-v0.1.json")


async def run_benchmark(fixture_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    gateway = get_search_gateway()
    policy = search_policy_from_env().model_copy(update={"cache_ttl_seconds": 0})
    mission_id = f"provider-benchmark-{uuid4()}"
    cases: list[dict] = []
    total_cost: dict[str, Decimal] = {}
    total_latency_ms = 0
    hits = 0

    for case in fixture["cases"]:
        response = await gateway.search(
            SearchRequest(
                query=case["query"],
                limit=10,
                mission_id=mission_id,
                correlation_id=mission_id,
            ),
            policy,
        )
        hosts = {
            (urlparse(str(result.url)).hostname or "").removeprefix("www.")
            for result in response.results
        }
        hit = case["expected_host"] in hosts
        hits += int(hit)
        latency_ms = sum(attempt.latency_ms for attempt in response.diagnostics.attempts)
        total_latency_ms += latency_ms
        for currency, amount in response.diagnostics.total_cost_by_currency.items():
            total_cost[currency] = total_cost.get(currency, Decimal("0")) + amount
        cases.append(
            {
                "id": case["id"],
                "expected_host": case["expected_host"],
                "hit": hit,
                "state": response.diagnostics.state,
                "selected_provider": response.diagnostics.selected_provider,
                "latency_ms": latency_ms,
                "result_count": len(response.results),
                "cost_by_currency": {
                    currency: str(amount)
                    for currency, amount in response.diagnostics.total_cost_by_currency.items()
                },
            }
        )

    count = len(cases)
    return {
        "schema_version": fixture["schema_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": count,
        "hits": hits,
        "recall_at_10": hits / count if count else 0,
        "total_latency_ms": total_latency_ms,
        "mean_latency_ms": total_latency_ms / count if count else 0,
        "total_cost_by_currency": {
            currency: str(amount)
            for currency, amount in total_cost.items()
        },
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run_benchmark(args.fixture))
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
