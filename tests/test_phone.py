from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.lead_qualifier import normalize_phone


def test_us_10_digit_numbers_become_e164() -> None:
    assert normalize_phone('2145550111') == '+12145550111'
    assert normalize_phone('(214) 555-0111') == '+12145550111'
    assert normalize_phone('214-555-0111') == '+12145550111'
    assert normalize_phone('214.555.0111') == '+12145550111'


def test_us_11_digit_numbers_with_leading_1_become_e164() -> None:
    assert normalize_phone('12145550111') == '+12145550111'
    assert normalize_phone('1-214-555-0111') == '+12145550111'
    assert normalize_phone('+1 214 555 0111') == '+12145550111'
    assert normalize_phone('+12145550111') == '+12145550111'


def test_phone_edge_cases() -> None:
    assert normalize_phone('') == ''
    assert normalize_phone(None) == ''
    assert normalize_phone('555-0111') == '5550111'
    assert normalize_phone('+44 20 7946 0991') == '+442079460991'


def test_api_stores_e164_phone() -> None:
    client = TestClient(app)
    payload = {
        'customer_name': 'Casey Nguyen',
        'phone': '(972) 555-0199',
        'email': 'casey@example.com',
        'service_type': 'cooling',
        'property_type': 'residential',
        'emergency': False,
        'address': '100 S Central Expy, Richardson, TX 75080',
        'source': 'website',
        'notes': 'Upstairs is warm',
    }
    response = client.post('/api/leads', json=payload)
    assert response.status_code == 200
    assert response.json()['phone'] == '+19725550199'

    preview = client.post('/api/ai/qualify', json=payload)
    assert preview.status_code == 200
    assert preview.json()['phone'] == '+19725550199'
