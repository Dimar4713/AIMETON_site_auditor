from pathlib import Path

main = Path("app/main.py")
text = main.read_text(encoding="utf-8")
marker = "from app.search_gateway import get_search_gateway, search_policy_from_env\n"
if "from app.search_regime_shadow import resolve_auto_search_regime\n" not in text:
    assert marker in text, "search gateway import marker missing"
    text = text.replace(marker, marker + "from app.search_regime_shadow import resolve_auto_search_regime\n", 1)

old = '''    payload["search_regime"] = {
        "requested": requested_regime,
        "effective": "balanced" if requested_regime == "auto" else requested_regime,
        "reason": "auto_balanced_default" if requested_regime == "auto" else "user_override",
        "routing_changed": False,
        "steering_enabled": False,
    }
'''
new = '''    if requested_regime == "auto":
        funnel = payload.get("funnel")
        if isinstance(funnel, dict):
            decision = resolve_auto_search_regime(
                raw_results=int(funnel.get("raw_results") or 0),
                unique_candidates=int(funnel.get("unique_candidates") or 0),
                qualified_candidates=int(funnel.get("qualified_candidates") or 0),
                duplicate_results=int(funnel.get("duplicate_results") or 0),
                excluded_results=int(funnel.get("excluded_results") or 0),
            )
            effective_regime = decision.effective
            regime_reason = decision.reason
        else:
            effective_regime = "balanced"
            regime_reason = "auto_balanced_default"
    else:
        effective_regime = requested_regime
        regime_reason = "user_override"

    payload["search_regime"] = {
        "requested": requested_regime,
        "effective": effective_regime,
        "reason": regime_reason,
        "routing_changed": False,
        "steering_enabled": False,
    }
'''
assert old in text, "hunt regime block marker missing"
main.write_text(text.replace(old, new, 1), encoding="utf-8")

tests = Path("tests/test_search_regime_shadow_api.py")
test_text = tests.read_text(encoding="utf-8")
addition = '''

@pytest.mark.asyncio
async def test_hunt_search_regime_auto_uses_observed_sparse_funnel(monkeypatch):
    async def sparse_run_hunt(_request):
        return {
            "region": "Красноярск",
            "candidates": [],
            "discovered": 2,
            "funnel": {
                "raw_results": 3,
                "unique_candidates": 2,
                "qualified_candidates": 1,
                "duplicate_results": 0,
                "excluded_results": 0,
            },
        }

    monkeypatch.setattr(main, "run_hunt", sparse_run_hunt)
    result = await main.hunt(
        HuntRequest(region="Красноярск", industries=[]),
        _request(),
    )

    metadata = result["search_regime"]
    assert metadata["requested"] == "auto"
    assert metadata["effective"] == "discovery"
    assert metadata["reason"] == "rarity_or_sparsity"
    assert metadata["routing_changed"] is False
    assert metadata["steering_enabled"] is False
'''
if "test_hunt_search_regime_auto_uses_observed_sparse_funnel" not in test_text:
    tests.write_text(test_text.rstrip() + addition.rstrip() + "\n", encoding="utf-8")
