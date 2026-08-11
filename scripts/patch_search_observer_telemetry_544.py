from pathlib import Path

path = Path("app/discovery.py")
text = path.read_text(encoding="utf-8")

old_import = "from app.search_gateway import (\n"
new_import = "from app.search_observer import build_search_wave_telemetry\nfrom app.search_gateway import (\n"
if new_import not in text:
    if old_import not in text:
        raise SystemExit("search_gateway import anchor not found")
    text = text.replace(old_import, new_import, 1)

old_block = '''    responses = await asyncio.gather(*(search_query(query) for query in queries))
    for response in responses:
        search_diagnostics.append(response.diagnostics)
        raw_results.extend(item.as_legacy_dict() for item in response.results)
    aggregate = SearchDiagnostics.aggregate(search_diagnostics)
'''
new_block = '''    responses = await asyncio.gather(*(search_query(query) for query in queries))
    wave_telemetry = build_search_wave_telemetry(queries, responses)
    trace.append(
        "hunt_search_wave_observed",
        state=TraceState.SUCCEEDED,
        reason_code="hunter_search_wave_observed",
        summary="Hunter search wave yield telemetry captured for shadow observer",
        counters={
            "query_count": wave_telemetry.query_count,
            "result_count": wave_telemetry.result_count,
            "unique_domain_count": wave_telemetry.unique_domain_count,
            "degraded_attempts": wave_telemetry.degraded_attempts,
            "latency_ms_total": wave_telemetry.latency_ms_total,
        },
        metadata={
            "observer_mode": "telemetry_only",
            "routing_changed": False,
            "duplicate_domain_ratio": wave_telemetry.duplicate_domain_ratio,
            "provider_result_counts": wave_telemetry.provider_result_counts,
            "attempt_states": wave_telemetry.attempt_states,
            "total_cost_by_currency": {
                key: str(value) for key, value in wave_telemetry.total_cost_by_currency.items()
            },
            "directions": [item.model_dump(mode="json") for item in wave_telemetry.directions],
        },
    )
    for response in responses:
        search_diagnostics.append(response.diagnostics)
        raw_results.extend(item.as_legacy_dict() for item in response.results)
    aggregate = SearchDiagnostics.aggregate(search_diagnostics)
'''
if new_block not in text:
    if old_block not in text:
        raise SystemExit("Hunter gather block anchor not found")
    text = text.replace(old_block, new_block, 1)

path.write_text(text, encoding="utf-8")
print("applied Phase A search observer telemetry integration")
