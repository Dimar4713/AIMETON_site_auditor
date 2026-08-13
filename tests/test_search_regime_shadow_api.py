from fastapi.testclient import TestClient

import app.main as main


async def _fake_run_hunt(_request):
    return {"region": "Красноярск", "candidates": [], "discovered": 0}


def test_hunt_search_regime_user_override_is_shadow_only(monkeypatch):
    monkeypatch.setattr(main, "run_hunt", _fake_run_hunt)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/hunt?search_regime=precision",
            json={"region": "Красноярск", "industries": ["стоматология"]},
        )

    assert response.status_code == 200
    metadata = response.json()["search_regime"]
    assert metadata == {
        "requested": "precision",
        "effective": "precision",
        "reason": "user_override",
        "routing_changed": False,
        "steering_enabled": False,
    }


def test_hunt_search_regime_auto_fails_safe_to_balanced_shadow(monkeypatch):
    monkeypatch.setattr(main, "run_hunt", _fake_run_hunt)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/hunt",
            json={"region": "Красноярск", "industries": []},
        )

    assert response.status_code == 200
    metadata = response.json()["search_regime"]
    assert metadata["requested"] == "auto"
    assert metadata["effective"] == "balanced"
    assert metadata["reason"] == "auto_balanced_default"
    assert metadata["routing_changed"] is False
    assert metadata["steering_enabled"] is False


def test_hunt_rejects_unknown_search_regime(monkeypatch):
    called = False

    async def fail_if_called(_request):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(main, "run_hunt", fail_if_called)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/hunt?search_regime=turbo",
            json={"region": "Красноярск", "industries": []},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_search_regime"
    assert called is False
