from pathlib import Path

path = Path('app/discovery.py')
text = path.read_text(encoding='utf-8')
text = text.replace('import asyncio\n', 'import asyncio\nimport os\n', 1)
text = text.replace(
    'from app.search_observer import build_search_wave_telemetry\n',
    'from app.search_observer import build_search_wave_telemetry\nfrom app.search_observer_llm import evaluate_search_wave_shadow\n',
    1,
)
anchor = '''    )\n    for response in responses:\n'''
insertion = '''    )\n\n    shadow_observer_enabled = os.getenv("HUNTER_SEARCH_OBSERVER_SHADOW_ENABLED", "").strip().lower() in {\n        "1", "true", "yes", "on"\n    }\n    if shadow_observer_enabled:\n        shadow_recommendation = await evaluate_search_wave_shadow(wave_telemetry)\n        if shadow_recommendation is None:\n            trace.append(\n                "hunt_search_wave_shadow_observer",\n                state=TraceState.SKIPPED,\n                reason_code="hunter_shadow_observer_unavailable",\n                summary="Shadow Search Observer produced no valid advisory recommendation",\n                counters={"recommendation_count": 0},\n                metadata={"observer_mode": "shadow", "routing_changed": False},\n            )\n        else:\n            action_counts: dict[str, int] = {}\n            for item in shadow_recommendation.recommendations:\n                action = str(item.action)\n                action_counts[action] = action_counts.get(action, 0) + 1\n            trace.append(\n                "hunt_search_wave_shadow_observer",\n                state=TraceState.SUCCEEDED,\n                reason_code="hunter_shadow_observer_advisory_captured",\n                summary="Shadow Search Observer advisory captured without execution",\n                counters={"recommendation_count": len(shadow_recommendation.recommendations)},\n                metadata={\n                    "observer_mode": "shadow",\n                    "routing_changed": False,\n                    "sufficient_evidence": shadow_recommendation.sufficient_evidence,\n                    "action_counts": action_counts,\n                    "summary": shadow_recommendation.summary,\n                },\n            )\n\n    for response in responses:\n'''
if anchor not in text:
    raise SystemExit('shadow observer insertion anchor not found')
text = text.replace(anchor, insertion, 1)
path.write_text(text, encoding='utf-8')
print('wired feature-flagged shadow observer')
