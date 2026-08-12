from app.hunter_forensic_trace import HunterForensicTrace
from app.trace_ledger import TraceState


def test_shadow_trace_attaches_call_local_observer_evidence(monkeypatch, tmp_path) -> None:
    from app import search_observer_llm as observer

    evidence = {
        "profile_name": "routerai-shadow-observer",
        "provider": "routerai",
        "model": "deepseek/deepseek-v3.2",
        "tier": "O1",
        "configured": True,
        "timeout_seconds": 20.0,
        "observer_latency_ms": 15471,
        "observer_outcome": "succeeded",
        "schema_valid": True,
        "observer_recommendation_count": 2,
    }
    monkeypatch.setattr(observer, "get_last_shadow_observer_evidence", lambda: evidence)

    trace = HunterForensicTrace("mission-1", "attempt-1", trace_db_path=tmp_path / "trace.sqlite3")
    captured = []
    monkeypatch.setattr(trace.ledger, "append", captured.append)

    trace.append(
        "hunt_search_wave_shadow_observer",
        state=TraceState.SUCCEEDED,
        reason_code="observer_ok",
        summary="shadow evidence",
        metadata={"observer_mode": "shadow", "routing_changed": False},
    )

    assert len(captured) == 1
    metadata = captured[0].metadata
    assert metadata["model"] == "deepseek/deepseek-v3.2"
    assert metadata["observer_latency_ms"] == 15471
    assert metadata["observer_outcome"] == "succeeded"
    assert metadata["routing_changed"] is False
    assert "api_key" not in metadata
    assert "base_url" not in metadata


def test_non_observer_trace_does_not_receive_observer_evidence(monkeypatch, tmp_path) -> None:
    from app import search_observer_llm as observer

    monkeypatch.setattr(
        observer,
        "get_last_shadow_observer_evidence",
        lambda: {"model": "should-not-appear"},
    )
    trace = HunterForensicTrace("mission-2", "attempt-2", trace_db_path=tmp_path / "trace.sqlite3")
    captured = []
    monkeypatch.setattr(trace.ledger, "append", captured.append)

    trace.append(
        "hunt_plan",
        state=TraceState.SUCCEEDED,
        reason_code="plan_ok",
        summary="plan",
        metadata={"plan_source": "test"},
    )

    assert len(captured) == 1
    assert "model" not in captured[0].metadata
