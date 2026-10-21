from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.seed import SAMPLE_LEADS
from app.main import app

LEAD_PAYLOAD = {
    'customer_name': 'Sarah Chen',
    'phone': '2145550111',
    'email': 'sarah@example.com',
    'service_type': 'heating',
    'property_type': 'residential',
    'emergency': True,
    'address': '1500 Main St, Dallas, TX 75201',
    'source': 'website',
    'notes': 'No heat in the house',
}


def test_public_routes_stay_open() -> None:
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    sales = client.get('/sales')
    assert sales.status_code == 200
    assert 'Book a demo' in sales.text
    assert 'mailto:hector@thefirstring.com' in sales.text
    assert client.get('/api/sales-offer').status_code == 200
    assert client.post('/api/leads', json=LEAD_PAYLOAD).status_code == 200


def test_lead_reads_require_login() -> None:
    anonymous = TestClient(app)
    assert anonymous.get('/api/dashboard').status_code == 401
    assert anonymous.get('/api/leads').status_code == 401
    assert anonymous.get('/api/leads/seed-0001').status_code == 401
    assert anonymous.post(
        '/api/leads/seed-0001/book',
        json={'appointment_time': '2026-10-22T09:00:00'},
    ).status_code == 401

    denied = anonymous.post('/api/login', json={'password': 'wrong-password'})
    assert denied.status_code == 401

    client = TestClient(app)
    logged_in = client.post('/api/login', json={'password': 'test-password'})
    assert logged_in.status_code == 200
    assert logged_in.json()['ok'] is True

    dashboard = client.get('/api/dashboard')
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body['total_leads'] >= len(SAMPLE_LEADS)
    assert body['booked_leads'] > 0
    assert body['emergency_leads'] > 0
    assert 'crm' in body
    assert body['crm']['total_leads'] == body['total_leads']

    leads = client.get('/api/leads')
    assert leads.status_code == 200
    ids = {lead['id'] for lead in leads.json()}
    assert 'seed-0001' in ids
    assert client.get('/api/leads/seed-0001').status_code == 200

    client.post('/api/logout')
    assert client.get('/api/leads').status_code == 401


def test_book_follow_up_and_review_round_trip() -> None:
    client = TestClient(app)
    assert client.post('/api/login', json={'password': 'test-password'}).status_code == 200
    created = client.post('/api/leads', json=LEAD_PAYLOAD)
    assert created.status_code == 200
    lead_id = created.json()['id']
    assert created.json()['phone'] == '+12145550111'

    booked = client.post(
        f'/api/leads/{lead_id}/book',
        json={'appointment_time': '2026-10-22T09:00:00', 'technician_name': 'Sam Ortiz', 'notes': 'Morning'},
    )
    assert booked.status_code == 200
    assert booked.json()['status'] == 'booked'
    assert booked.json()['technician_name'] == 'Sam Ortiz'

    follow_up = client.post(f'/api/leads/{lead_id}/follow-up', json={'channel': 'sms'})
    assert follow_up.status_code == 200
    assert follow_up.json()['lead_id'] == lead_id

    review = client.post(f'/api/leads/{lead_id}/review-request', json={})
    assert review.status_code == 200
    assert review.json()['lead_id'] == lead_id

    fetched = client.get(f'/api/leads/{lead_id}')
    assert fetched.status_code == 200
    assert fetched.json()['review_requested'] is True
    assert fetched.json()['status'] == 'review_requested'


def test_unset_password_locks_dashboard(monkeypatch) -> None:
    monkeypatch.setenv('DASHBOARD_PASSWORD', '')
    client = TestClient(app)
    assert client.get('/api/session').json() == {'configured': False, 'authenticated': False}
    assert client.get('/api/dashboard').status_code == 401
    assert client.get('/api/leads').status_code == 401
    login = client.post('/api/login', json={'password': 'test-password'})
    assert login.status_code == 503
    assert client.get('/health').status_code == 200
    assert client.get('/sales').status_code == 200
