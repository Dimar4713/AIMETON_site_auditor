from app.search_observer_models import observer_profile


def test_routerai_backed_chinese_profiles_share_existing_credential(monkeypatch) -> None:
    monkeypatch.setenv("ROUTERAI_API_KEY", "test-key")
    monkeypatch.delenv("ROUTERAI_QWEN_OBSERVER_MODEL", raising=False)
    monkeypatch.delenv("ROUTERAI_GLM_OBSERVER_MODEL", raising=False)
    monkeypatch.delenv("ROUTERAI_DEEPSEEK_OBSERVER_MODEL", raising=False)

    expected = {
        "routerai-qwen35-9b": "qwen/qwen3.5-9b",
        "routerai-glm47-flash": "z-ai/glm-4.7-flash",
        "routerai-deepseek-v32": "deepseek/deepseek-v3.2",
    }
    for name, model in expected.items():
        resolved = observer_profile(name).resolve()
        assert resolved.configured is True
        assert resolved.provider.value == "routerai"
        assert resolved.base_url == "https://api.routerai.ru/v1"
        assert resolved.model == model
        assert resolved.tier == "O1"
        assert "api_key" not in resolved.safe_descriptor()


def test_routerai_backed_model_ids_remain_overridable(monkeypatch) -> None:
    monkeypatch.setenv("ROUTERAI_API_KEY", "test-key")
    monkeypatch.setenv("ROUTERAI_QWEN_OBSERVER_MODEL", "qwen/future-fast-model")
    resolved = observer_profile("routerai-qwen35-9b").resolve()
    assert resolved.model == "qwen/future-fast-model"
