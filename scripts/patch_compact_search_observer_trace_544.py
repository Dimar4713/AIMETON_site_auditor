from pathlib import Path

path = Path('app/discovery.py')
text = path.read_text(encoding='utf-8')
old = '''        metadata={
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
'''
new = '''        metadata={
            "observer_mode": "telemetry_only",
            "routing_changed": False,
            "duplicate_domain_ratio": wave_telemetry.duplicate_domain_ratio,
            "provider_result_counts": wave_telemetry.provider_result_counts,
            "attempt_states": wave_telemetry.attempt_states,
            "total_cost_by_currency": {
                key: str(value) for key, value in wave_telemetry.total_cost_by_currency.items()
            },
            "direction_count": len(wave_telemetry.directions),
            "direction_yield_preview": [
                (
                    f"{index}:results={item.result_count};domains={item.unique_domain_count};"
                    f"dup={item.duplicate_domain_ratio};latency_ms={item.latency_ms_total};"
                    f"degraded={item.degraded_attempts};cache={str(item.cache_hit).lower()}"
                )
                for index, item in enumerate(wave_telemetry.directions)
            ],
        },
'''
if old not in text:
    raise SystemExit('observer metadata block anchor not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('compacted search observer trace metadata')
