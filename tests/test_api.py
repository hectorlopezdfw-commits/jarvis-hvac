from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_submit_lead() -> None:
    client = TestClient(app)
    payload = {
        'customer_name': 'Sarah Bell',
        'phone': '2145550111',
        'email': 'sarah@example.com',
        'service_type': 'heating',
        'property_type': 'residential',
        'emergency': True,
        'address': '1500 Main St',
        'source': 'website',
        'notes': 'No heat in the house',
    }

    response = client.post('/api/leads', json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body['priority_label'] in {'high', 'critical'}
    assert body['status'] == 'new'


def test_sales_offer_endpoint() -> None:
    client = TestClient(app)
    response = client.get('/api/sales-offer')
    assert response.status_code == 200
    data = response.json()
    assert 'title' in data
    assert 'pricing' in data
