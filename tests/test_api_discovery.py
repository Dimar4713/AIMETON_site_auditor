from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_llms_txt_is_plain_text_and_points_to_openapi():
    response = client.get('/llms.txt')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    assert '/openapi.json' in response.text
    assert '/api/capabilities' in response.text
    assert 'JavaScript' in response.text


def test_capabilities_exposes_agent_readable_discovery_links():
    response = client.get('/api/capabilities')
    assert response.status_code == 200
    payload = response.json()
    assert payload['openapi_json'] == '/openapi.json'
    assert payload['plain_text_docs'] == '/api/docs.txt'
    assert payload['llms_txt'] == '/llms.txt'
    assert payload['swagger_ui'] == '/docs'
    assert payload['health'] == '/api/health'
    assert payload['javascript_required'] is False


def test_plain_text_docs_are_readable_without_javascript():
    response = client.get('/api/docs.txt')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    body = response.text
    assert '/openapi.json' in body
    assert '/api/capabilities' in body
    assert '/llms.txt' in body


def test_health_advertises_machine_readable_api_discovery():
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['openapi'] == '/openapi.json'
    assert payload['capabilities'] == '/api/capabilities'
    assert payload['api_docs_text'] == '/api/docs.txt'
    assert payload['llms_txt'] == '/llms.txt'
