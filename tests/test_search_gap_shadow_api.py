import pytest
from starlette.requests import Request

import app.main as main
from app.models import HuntRequest


def _request(query=""):
    return Request({"type":"http","method":"POST","path":"/api/hunt","query_string":query.encode(),"headers":[],"client":("test",1),"server":("test",80),"scheme":"http"})


@pytest.mark.asyncio
async def test_sparse_hunt_exposes_shadow_gap_refinement(monkeypatch):
    async def fake(_request):
        return {"region":"Красноярск","queries":["стоматология Красноярск контакты"],"candidates":[],"discovered":2,"funnel":{"raw_results":3,"unique_candidates":2,"qualified_candidates":1,"returned_candidates":0,"duplicate_results":0,"excluded_results":0}}
    monkeypatch.setattr(main, "run_hunt", fake)
    result = await main.hunt(HuntRequest(region="Красноярск", industries=["стоматология"]), _request())
    shadow = result["search_refinement_shadow"]
    codes = {item["code"] for item in shadow["gaps"]}
    assert result["search_regime"]["effective"] == "discovery"
    assert "sparse_yield" in codes
    assert "discovery_novelty_unmeasured" in codes
    assert shadow["suggestion_count"] > 0
    assert shadow["routing_changed"] is False
    assert shadow["steering_enabled"] is False
