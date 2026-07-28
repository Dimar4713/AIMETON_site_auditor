from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.document_pipeline import (
    DocumentPipeline,
    DocumentRequest,
    RawDocument,
    StaticHttpFetcher,
)


BENCHMARK = ROOT / "benchmarks" / "sef" / "document-fetch-5-v0.1.json"


class FixtureFetcher(StaticHttpFetcher):
    def __init__(self, fixtures: dict[str, Path]) -> None:
        self._fixtures = fixtures

    async def fetch(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int,
    ) -> RawDocument:
        del timeout_seconds, max_redirects
        html = self._fixtures[url].read_text(encoding="utf-8")
        if len(html.encode("utf-8")) > max_bytes:
            raise ValueError("fixture exceeds benchmark size limit")
        return RawDocument(
            final_url=url,
            title="",
            html=html,
            media_type="text/html",
            path="static",
        )


async def run() -> dict:
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    fixtures = {
        case["url"]: ROOT / case["fixture"]
        for case in benchmark["cases"]
    }
    pipeline = DocumentPipeline(static_fetcher=FixtureFetcher(fixtures))
    cases: list[dict] = []
    for case in benchmark["cases"]:
        result = await pipeline.fetch(
            DocumentRequest(
                mission_id=f"mission_{case['case_id'].lower()}",
                source_id=f"source_{case['case_id'].lower()}",
                correlation_id=f"corr_{case['case_id'].lower()}",
                url=case["url"],
            )
        )
        passed = case["required_text"] in result.normalized_text
        cases.append(
            {
                "case_id": case["case_id"],
                "passed": passed,
                "path": result.diagnostics.path.value,
                "blocks": len(result.blocks),
                "tables": len(result.tables),
                "links": len(result.links),
                "document_digest": result.normalized_content_digest,
            }
        )
    success_rate = sum(item["passed"] for item in cases) / len(cases)
    return {
        "benchmark_id": benchmark["benchmark_id"],
        "version": benchmark["version"],
        "passed": sum(item["passed"] for item in cases),
        "total": len(cases),
        "success_rate": success_rate,
        "minimum_success_rate": benchmark["minimum_success_rate"],
        "gate": "passed" if success_rate >= benchmark["minimum_success_rate"] else "failed",
        "cases": cases,
    }


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["gate"] == "passed" else 1)
