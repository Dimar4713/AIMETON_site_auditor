from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import IntelligenceSource


def test_sa01_health_and_mcp_contracts_work_together():
    client = TestClient(app)
    health = client.get('/api/health')
    redirect = client.get('/mcp', follow_redirects=False)

    assert health.status_code == 200
    assert health.json()['status'] == 'ok'
    assert health.json()['version'] == '0.6.1'
    assert redirect.status_code == 307
    assert redirect.headers['location'] == '/mcp/'


def test_sa01_search_hint_contract_cannot_claim_evidence():
    source = IntelligenceSource(
        id='I1',
        title='Search result',
        url='https://example.org/result',
        snippet='Unverified snippet',
        accessed_at='2026-07-22T00:00:00+00:00',
        query_kind='finance',
        result_kind='finance',
        source_class='unknown',
        classification_state='classified',
    )

    assert source.lifecycle_state == 'discovery_hint'
    assert source.evidence_level == 'unverified_mention'
    assert source.document_url is None
    assert source.evidence_quote is None
