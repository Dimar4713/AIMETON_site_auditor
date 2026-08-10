from __future__ import annotations

from collections import Counter
import json
import sqlite3
from urllib.parse import urlparse

from app.hunter_lead_fit import classify_lead_fit, lead_fit_rank


DB_PATH = "/app/data/runtime-core.sqlite3"
TARGET_FUNNEL = {
    "raw_results": 594,
    "unique_candidates": 145,
    "qualified_candidates": 88,
    "returned_candidates": 88,
}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def load_json(value: str | None) -> dict:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def score_value(metadata: dict) -> int:
    for key in ("final_score", "preliminary_score"):
        value = metadata.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return -1


def main() -> None:
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    funnel_rows = db.execute(
        """
        SELECT mission_id, attempt_id, created_at, counters_json
        FROM mission_trace_events
        WHERE component = 'hunter' AND operation = 'hunt_funnel_complete'
        ORDER BY created_at DESC
        """
    ).fetchall()

    target = None
    target_counters: dict = {}
    for row in funnel_rows:
        counters = load_json(row["counters_json"])
        if all(counters.get(key) == value for key, value in TARGET_FUNNEL.items()):
            target = row
            target_counters = counters
            break

    assert target is not None, (
        "saved 594→145→88→88 Hunter forensic mission is unavailable; "
        "do not substitute a provider-backed rerun"
    )

    rows = db.execute(
        """
        SELECT sequence, metadata_json, created_at
        FROM mission_trace_events
        WHERE mission_id = ? AND attempt_id = ?
          AND component = 'hunter' AND operation = 'candidate_returned'
        ORDER BY sequence
        """,
        (target["mission_id"], target["attempt_id"]),
    ).fetchall()
    db.close()

    assert len(rows) == 88, f"expected 88 saved returned candidates, got {len(rows)}"

    records: list[dict] = []
    for old_rank, row in enumerate(rows, start=1):
        metadata = load_json(row["metadata_json"])
        url = str(metadata.get("candidate_url") or "")
        title = str(metadata.get("candidate_title") or "")
        source_role = str(metadata.get("source_role") or "")
        assert url, f"candidate_returned sequence {row['sequence']} lacks candidate_url"
        assert title, f"candidate_returned sequence {row['sequence']} lacks candidate_title"
        assert source_role, f"candidate_returned sequence {row['sequence']} lacks source_role"

        assessment = classify_lead_fit(
            title=title,
            snippet="",
            url=url,
            source_role=source_role,
        )
        records.append(
            {
                "old_rank": old_rank,
                "sequence": int(row["sequence"]),
                "title": title,
                "url": url,
                "host": host(url),
                "source_role": source_role,
                "lead_fit": assessment.fit,
                "reason": assessment.reason,
                "evidence": list(assessment.evidence),
                "score": score_value(metadata),
            }
        )

    role_counts = Counter(item["source_role"] for item in records)
    fit_counts = Counter(item["lead_fit"] for item in records)
    direct = [item for item in records if item["source_role"] == "direct_candidate"]
    direct_fit_counts = Counter(item["lead_fit"] for item in direct)

    assert len(direct) == 57, f"expected 57 direct candidates from saved E2E, got {len(direct)}"
    assert fit_counts["not_applicable"] == len(records) - len(direct)
    assert direct_fit_counts["commercial_candidate"] >= 1, direct_fit_counts
    assert direct_fit_counts["institutional_candidate"] >= 1, direct_fit_counts

    # Strong host evidence must always classify as institutional.
    gosuslugi = [item for item in direct if item["host"].endswith("gosuslugi.ru")]
    assert gosuslugi, "saved E2E contains no gosuslugi direct candidate"
    assert all(item["lead_fit"] == "institutional_candidate" for item in gosuslugi), gosuslugi

    # Conservative controls: known branded direct sites must not be guessed private/public.
    for control_host in ("sapfircs.ru", "krasnoyarsk.rzd-medicine.ru"):
        control = [item for item in direct if item["host"] == control_host]
        if control:
            assert all(item["lead_fit"] == "unknown_candidate" for item in control), control

    # If explicit private examples are present in the saved result, they must be promoted.
    explicit_private_hosts = {"aldenta.ru", "24denta.ru", "aleksdent24.ru"}
    explicit_private = [item for item in direct if item["host"] in explicit_private_hosts]
    assert explicit_private, "saved E2E contains none of the explicit private control sites"
    assert any(item["lead_fit"] == "commercial_candidate" for item in explicit_private), explicit_private

    reranked_direct = sorted(
        direct,
        key=lambda item: (lead_fit_rank(item["lead_fit"]), item["score"]),
        reverse=True,
    )
    seen_institutional = False
    for item in reranked_direct:
        if item["lead_fit"] == "institutional_candidate":
            seen_institutional = True
        elif seen_institutional:
            raise AssertionError(
                "commercial/unknown direct candidate ranked below institutional candidate"
            )

    commercial_positions = [item["old_rank"] for item in records if item["lead_fit"] == "commercial_candidate"]
    institutional_positions = [item["old_rank"] for item in records if item["lead_fit"] == "institutional_candidate"]

    print("## Hunter lead-fit zero-cost Stage replay")
    print()
    print(f"- saved mission: `{target['mission_id']}`")
    print(f"- saved attempt: `{target['attempt_id']}`")
    print(f"- saved funnel timestamp: `{target['created_at']}`")
    print(
        "- saved funnel: "
        f"`{target_counters.get('raw_results')} raw → "
        f"{target_counters.get('unique_candidates')} unique → "
        f"{target_counters.get('qualified_candidates')} qualified → "
        f"{target_counters.get('returned_candidates')} returned`"
    )
    print("- provider calls during replay: `0`")
    print(f"- saved source-role distribution: `{dict(sorted(role_counts.items()))}`")
    print(f"- replay lead-fit distribution (all): `{dict(sorted(fit_counts.items()))}`")
    print(f"- replay lead-fit distribution (57 direct): `{dict(sorted(direct_fit_counts.items()))}`")
    print(f"- explicit private controls found: `{len(explicit_private)}`")
    print(f"- gosuslugi institutional controls found: `{len(gosuslugi)}`")
    print(f"- prior positions of commercial-classified direct sites: `{commercial_positions}`")
    print(f"- prior positions of institutional-classified direct sites: `{institutional_positions}`")
    print()
    print("### Re-ranked direct top 25")
    print()
    print("| new | old | lead_fit | score | host | title |")
    print("|---:|---:|---|---:|---|---|")
    for new_rank, item in enumerate(reranked_direct[:25], start=1):
        safe_title = item["title"].replace("|", "/")[:100]
        print(
            f"| {new_rank} | {item['old_rank']} | {item['lead_fit']} | "
            f"{item['score']} | `{item['host']}` | {safe_title} |"
        )
    print()
    print("### Institutional controls")
    print()
    for item in [entry for entry in direct if entry["lead_fit"] == "institutional_candidate"]:
        print(
            f"- old #{item['old_rank']}: `{item['host']}` — {item['title'][:120]} "
            f"— evidence `{item['evidence']}`"
        )
    print()
    print("### Verdict")
    print()
    print(
        "✅ Saved real Stage E2E candidates replay successfully through the deployed lead-fit classifier: "
        "commercial > unknown > institutional within direct candidates; supporting/possible sources remain outside lead-fit."
    )


if __name__ == "__main__":
    main()
