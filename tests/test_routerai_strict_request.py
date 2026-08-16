from __future__ import annotations

import asyncio
import json

import pytest

import app.routerai_strict_request as strict
from app.routerai_profile_extraction import ManagementSlice
from app.routerai_split_synthesis import SplitSynthesisPhaseError


def _management_content() -> str:
    return json.dumps(
        {
            "company_facts": [
                {
                    "field": "executives",
                    "value": "Named executive",
                    "period": None,
                    "confidence": "Средняя",
                    "source_ids": ["S1"],
                }
            ],
            "risks_and_assumptions": [],
        },
        ensure_ascii=False,
    )


def test_strict_request_uses_provider_json_schema(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": _management_content()},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, json):
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setenv("ROUTERAI_API_KEY", "test-only")
    monkeypatch.setattr(strict.httpx, "AsyncClient", lambda timeout: FakeClient())

    result = asyncio.run(
        strict.request_json_strict(
            "profile_management",
            ManagementSlice,
            system="Structured only",
            prompt="Extract management",
            max_tokens=600,
            timeout_seconds=1,
        )
    )

    payload = captured["payload"]
    assert payload["structured_outputs"] is True
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["name"] == "profile_management"
    assert payload["response_format"]["json_schema"]["schema"] == ManagementSlice.model_json_schema()
    assert result.company_facts[0].field == "executives"


def test_strict_request_surfaces_output_truncation(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "{}"},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, json):
            return FakeResponse()

    monkeypatch.setenv("ROUTERAI_API_KEY", "test-only")
    monkeypatch.setattr(strict.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(SplitSynthesisPhaseError) as exc_info:
        asyncio.run(
            strict.request_json_strict(
                "profile_management",
                ManagementSlice,
                system="Structured only",
                prompt="Extract management",
                max_tokens=600,
                timeout_seconds=1,
            )
        )

    assert exc_info.value.phase == "profile_management"
    assert exc_info.value.error_type == "OutputTruncated"
