import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.main as main
from app.models import HuntRequest


def _request(query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/hunt",
            "query_string": query.encode("utf-8"),
            "headers": [],
            "client": ("test", 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


async def _fake_run_hunt(_request):
    return {"region": "Красноярск", "candidates": [], "discovered": 0}


@pytest.mark.asyncio
async def test_hunt_search_regime_user_override_is_shadow_only(monkeypatch):
    monkeypatch.setattr(main, "run_hunt", _fake_run_hunt)

    result = await main.hunt(
        HuntRequest(region="Красноярск", industries=["стоматология"]),
        _request("search_regime=precision"),
    )

    assert result["search_regime"] == {
        "requested": "precision",
        "effective": "precision",
        "reason": "user_override",
        "routing_changed": False,
        "steering_enabled": False,
    }


@pytest.mark.asyncio
async def test_hunt_search_regime_auto_fails_safe_to_balanced_shadow(monkeypatch):
    monkeypatch.setattr(main, "run_hunt", _fake_run_hunt)

    result = await main.hunt(
        HuntRequest(region="Красноярск", industries=[]),
        _request(),
    )

    metadata = result["search_regime"]
    assert metadata["requested"] == "auto"
    assert metadata["effective"] == "balanced"
    assert metadata["reason"] == "auto_balanced_default"
    assert metadata["routing_changed"] is False
    assert metadata["steering_enabled"] is False


@pytest.mark.asyncio
async def test_hunt_rejects_unknown_search_regime(monkeypatch):
    called = False

    async def fail_if_called(_request):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(main, "run_hunt", fail_if_called)

    with pytest.raises(HTTPException) as exc_info:
        await main.hunt(
            HuntRequest(region="Красноярск", industries=[]),
            _request("search_regime=turbo"),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "invalid_search_regime"
    assert called is False
