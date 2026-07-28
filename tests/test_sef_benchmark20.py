from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).parents[1]
BENCHMARK_PATH = ROOT / "benchmarks" / "sef" / "benchmark-20-v0.1.json"
GOLDEN_PATH = ROOT / "benchmarks" / "sef" / "golden-5-v0.1.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_benchmark20_cohort_is_frozen_and_balanced():
    benchmark = _load(BENCHMARK_PATH)
    cases = benchmark["cases"]

    assert benchmark["benchmark_id"] == "SEF-BENCHMARK-20"
    assert benchmark["version"] == "0.1.0"
    assert benchmark["status"] == "frozen"
    assert len(cases) == benchmark["cohort_contract"]["case_count"] == 20
    assert len({case["id"] for case in cases}) == 20

    industry_counts = Counter(case["industry"] for case in cases)
    assert len(industry_counts) == benchmark["cohort_contract"]["industry_count"] == 4
    assert set(industry_counts.values()) == {benchmark["cohort_contract"]["cases_per_industry"]}

    footprints = {case["digital_footprint"] for case in cases}
    assert footprints == set(benchmark["cohort_contract"]["required_footprint_bands"])


def test_benchmark20_urls_and_ids_are_canonical():
    benchmark = _load(BENCHMARK_PATH)

    for ordinal, case in enumerate(benchmark["cases"], start=1):
        assert case["id"] == f"SEF-B20-{ordinal:02d}"
        parsed = urlparse(case["official_url"])
        assert parsed.scheme == "https"
        assert parsed.hostname
        assert case["query_name"].strip()
        assert case["region"].strip()


def test_first_five_cases_have_manual_identity_ground_truth():
    benchmark = _load(BENCHMARK_PATH)
    golden = _load(GOLDEN_PATH)
    golden_cases = {case["case_id"]: case for case in golden["cases"]}
    required = set(benchmark["cohort_contract"]["required_fact_types"])

    assert golden["benchmark_version"] == benchmark["version"]
    assert golden["status"] == "frozen"
    assert len(golden_cases) == benchmark["cohort_contract"]["manual_golden_case_count"] == 5

    for case in benchmark["cases"][:5]:
        assert case["golden_status"] == "manual_v0.1"
        facts = golden_cases[case["id"]]["facts"]
        predicates = {fact["predicate"] for fact in facts}
        assert required <= predicates
        assert all(fact["verification_status"] == "verified" for fact in facts)


def test_golden_sources_are_first_party_and_not_search_snippets():
    benchmark = _load(BENCHMARK_PATH)
    benchmark_hosts = {
        case["id"]: urlparse(case["official_url"]).hostname.removeprefix("www.")
        for case in benchmark["cases"]
    }
    golden = _load(GOLDEN_PATH)

    assert golden["rules"]["llm_is_source"] is False
    assert golden["rules"]["search_snippet_is_evidence"] is False

    for case in golden["cases"]:
        expected_host = benchmark_hosts[case["case_id"]]
        for fact in case["facts"]:
            source = fact["source"]
            source_host = urlparse(source["url"]).hostname.removeprefix("www.")
            assert source["evidence_tier"].startswith("T2_official_company")
            assert source_host == expected_host or source_host.endswith(f".{expected_host}")
            assert source["locator"].strip()
            assert source["accessed_at"] == golden["verified_at"]
