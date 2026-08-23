from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import accb_routerai_readonly_census as census


def test_failure_receipt_preserves_zero_generation_and_zero_spend() -> None:
    result = census.failure_receipt(
        census.CensusError("no healthy priced endpoint supports all Layer B anchors for z-ai/glm-5.2")
    )

    assert result["status"] == "FRESH_READ_ONLY_CENSUS_FAILED"
    assert result["whole_tranche_conservative_estimate_rub"] is None
    assert result["http_methods"] == ["GET"]
    assert result["routerai_authorization_header_sent"] is False
    assert result["provider_generations_performed"] == 0
    assert result["paid_spend_authorized_rub"] == 0
    assert result["failure"]["error_type"] == "CensusError"
    assert "z-ai/glm-5.2" in result["failure"]["safe_message"]


def test_unexpected_failure_retains_only_hash_not_raw_exception() -> None:
    secret_marker = "RAW_PROVIDER_TEXT_MUST_NOT_BE_RETAINED"
    result = census.failure_receipt(ValueError(secret_marker))

    assert result["failure"]["safe_message"].startswith("unexpected internal census failure")
    assert secret_marker not in str(result)
    assert len(result["failure"]["exception_repr_sha256"]) == 64


def test_http_error_body_is_hashed_not_retained(monkeypatch) -> None:
    raw = b"SENSITIVE_ROUTERAI_ERROR_BODY"
    error = urllib.error.HTTPError(
        census.BASE_URL + "/models/z-ai/glm-5.2/endpoints",
        503,
        "Service Unavailable",
        hdrs=None,
        fp=BytesIO(raw),
    )

    def fail_urlopen(*args, **kwargs):
        raise error

    monkeypatch.setattr(census.urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(census.CensusError) as excinfo:
        census.get_json(census.BASE_URL + "/models/z-ai/glm-5.2/endpoints")

    message = str(excinfo.value)
    assert "HTTP 503" in message
    assert "body_sha256=" in message
    assert raw.decode() not in message


def test_main_writes_failure_receipt_and_returns_nonzero(monkeypatch, tmp_path) -> None:
    output = tmp_path / "receipt.json"

    def fail_census():
        raise census.CensusError("synthetic admission failure")

    monkeypatch.setattr(census, "census", fail_census)
    monkeypatch.setattr(sys, "argv", ["accb_routerai_readonly_census.py", "--output", str(output)])

    rc = census.main()
    payload = output.read_text(encoding="utf-8")

    assert rc == 2
    assert '"status": "FRESH_READ_ONLY_CENSUS_FAILED"' in payload
    assert '"provider_generations_performed": 0' in payload
    assert '"paid_spend_authorized_rub": 0' in payload
