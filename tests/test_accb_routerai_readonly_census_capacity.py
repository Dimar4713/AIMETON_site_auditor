from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_readonly_census as census


def test_endpoint_with_insufficient_completion_capacity_fails_closed() -> None:
    body = {
        "data": {
            "endpoints": [
                {
                    "provider_name": "Fixture",
                    "tag": "fixture",
                    "status": 0,
                    "context_length": 1_048_576,
                    "max_prompt_tokens": 900_000,
                    "max_completion_tokens": 4096,
                    "supported_apis": ["chat"],
                    "supported_parameters": ["max_tokens"],
                    "pricing": {"prompt": 0.001, "completion": 0.002},
                    "variable_pricings": [],
                }
            ]
        }
    }

    with pytest.raises(census.CensusError, match="no healthy priced endpoint supports all Layer B anchors"):
        census.select_endpoint("z-ai/glm-5.2", body)
