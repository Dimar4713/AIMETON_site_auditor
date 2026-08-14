from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from app.trace_ledger import TraceEvent


def _attempt_key(event: TraceEvent) -> tuple[str, str]:
    return event.mission_id, event.attempt_id


def _host(value: object) -> str:
    try:
        host = (urlsplit(str(value or "")).hostname or "").lower()
    except Exception:
        return ""
    return host.removeprefix("www.")


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def build_latest_hunter_provider_attribution(
    events: list[TraceEvent],
    *,
    minimum_query_count: int = 20,
) -> dict[str, object]:
    """Build aggregate provider contribution for the latest substantial Hunter attempt.

    The result deliberately exports no mission/attempt identity, query text, URL or
    domain names. It is intended for read-only Stage evidence about provider yield
    and retained normalized contribution.
    """
    query_events = [
        event
        for event in events
        if event.component == "search_gateway" and event.operation == "query_planned"
    ]
    funnel_attempts = {
        _attempt_key(event)
        for event in events
        if event.component == "hunter" and event.operation == "hunt_funnel_complete"
    }

    by_attempt: dict[tuple[str, str], list[TraceEvent]] = defaultdict(list)
    for event in query_events:
        if _attempt_key(event) in funnel_attempts:
            by_attempt[_attempt_key(event)].append(event)

    eligible = [
        (key, rows)
        for key, rows in by_attempt.items()
        if len(rows) >= minimum_query_count
    ]
    if not eligible:
        return {
            "evidence_kind": "search_provider_attribution_inventory",
            "qualifying_attempt_found": False,
            "minimum_query_count": minimum_query_count,
            "query_count": 0,
            "provider_call_count": {},
            "provider_raw_result_count": {},
            "provider_cost_by_currency": {},
            "retained_result_item_count": 0,
            "retained_unique_domain_count": 0,
            "retained_primary_provider_domain_count": {},
            "retained_provider_support_domain_count": {},
            "retained_corroborated_domain_count": 0,
            "routing_changed": False,
        }

    attempt, selected_queries = max(
        eligible,
        key=lambda pair: max(event.created_at for event in pair[1]),
    )
    selected = [event for event in events if _attempt_key(event) == attempt]

    responses = [
        event
        for event in selected
        if event.component == "search_gateway" and event.operation == "response_received"
    ]
    result_items = [
        event
        for event in selected
        if event.component == "search_gateway" and event.operation == "result_item"
    ]

    provider_calls: dict[str, int] = defaultdict(int)
    provider_raw: dict[str, int] = defaultdict(int)
    costs: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for event in responses:
        provider = str(event.provider or "unknown")
        provider_calls[provider] += 1
        provider_raw[provider] += int(event.counters.get("results_received", 0) or 0)
        currency = str(event.metadata.get("cost_currency") or "")
        if currency:
            costs[provider][currency] += _decimal(event.metadata.get("cost_amount"))

    domains: dict[str, dict[str, object]] = {}
    for event in result_items:
        host = _host(event.metadata.get("result_url"))
        if not host:
            continue
        primary = str(event.provider or "unknown")
        support = {primary}
        corroborated = event.metadata.get("corroborated_by") or []
        if isinstance(corroborated, (list, tuple, set)):
            support.update(str(item) for item in corroborated if str(item))
        row = domains.setdefault(host, {"primary": primary, "support": set()})
        row["support"].update(support)  # type: ignore[union-attr]

    primary_counts: dict[str, int] = defaultdict(int)
    support_counts: dict[str, int] = defaultdict(int)
    corroborated_count = 0
    for row in domains.values():
        primary_counts[str(row["primary"])] += 1
        support = sorted(str(item) for item in row["support"])  # type: ignore[union-attr]
        support_counts["+".join(support) if support else "unknown"] += 1
        if len(support) > 1:
            corroborated_count += 1

    serialized_costs = {
        provider: {currency: str(amount) for currency, amount in sorted(per_currency.items())}
        for provider, per_currency in sorted(costs.items())
    }
    return {
        "evidence_kind": "search_provider_attribution_inventory",
        "qualifying_attempt_found": True,
        "minimum_query_count": minimum_query_count,
        "query_count": len(selected_queries),
        "provider_call_count": dict(sorted(provider_calls.items())),
        "provider_raw_result_count": dict(sorted(provider_raw.items())),
        "provider_cost_by_currency": serialized_costs,
        "retained_result_item_count": len(result_items),
        "retained_unique_domain_count": len(domains),
        "retained_primary_provider_domain_count": dict(sorted(primary_counts.items())),
        "retained_provider_support_domain_count": dict(sorted(support_counts.items())),
        "retained_corroborated_domain_count": corroborated_count,
        "routing_changed": False,
    }
