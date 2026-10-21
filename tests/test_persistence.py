from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.db.seed import SAMPLE_LEADS
from app.db.store import SqlLeadStore, project_root, resolve_database_url


def _url(path: Path) -> str:
    return 'sqlite:///' + path.as_posix()


def test_database_url_resolution() -> None:
    sqlite_url = resolve_database_url('')
    sqlite_path = Path(sqlite_url.removeprefix('sqlite:///'))
    assert sqlite_path == project_root() / 'data' / 'jarvis.db'
    assert sqlite_path.parent.is_dir()
    assert resolve_database_url('postgres://user:pass@localhost:5432/jarvis').startswith('postgresql+psycopg://')
    assert resolve_database_url('postgresql://user:pass@localhost/jarvis').startswith('postgresql+psycopg://')


def test_seed_is_idempotent_and_non_empty(tmp_path: Path) -> None:
    url = _url(tmp_path / 'leads.db')
    first = SqlLeadStore(url)
    leads = first.list()
    assert 8 <= len(SAMPLE_LEADS) <= 12
    assert len(leads) == len(SAMPLE_LEADS)

    ids = [lead['id'] for lead in leads]
    assert len(ids) == len(set(ids))
    assert any(lead['property_type'] == 'residential' for lead in leads)
    assert any(lead['property_type'] == 'commercial' for lead in leads)
    assert any(lead['emergency'] for lead in leads)
    assert any(lead['status'] == 'booked' for lead in leads)
    assert any(lead['status'] != 'booked' for lead in leads)
    for lead in leads:
        assert lead['phone'].startswith('+1')
        assert '555' in lead['phone']
        assert 'TX' in lead['address']

    first.dispose()
    second = SqlLeadStore(url)
    assert [lead['id'] for lead in second.list()] == ids
    second.dispose()


def test_lead_survives_a_new_store_instance(tmp_path: Path) -> None:
    url = _url(tmp_path / 'leads.db')
    first = SqlLeadStore(url)
    created = first.create(
        {
            'customer_name': 'Pat Reyes',
            'phone': '+12145550199',
            'service_type': 'heating',
            'property_type': 'residential',
            'emergency': True,
            'status': 'new',
            'priority_score': 90,
            'priority_label': 'critical',
        }
    )
    first.dispose()

    second = SqlLeadStore(url)
    loaded = second.get(created['id'])
    assert loaded is not None
    assert loaded['customer_name'] == 'Pat Reyes'
    assert loaded['phone'] == '+12145550199'
    assert loaded['emergency'] is True
    second.update(
        created['id'],
        {'status': 'booked', 'appointment_time': '2026-10-22T15:00:00', 'technician_name': 'Sam Ortiz'},
    )
    second.dispose()

    third = SqlLeadStore(url)
    booked = third.get(created['id'])
    assert booked is not None
    assert booked['status'] == 'booked'
    assert booked['appointment_time'] == '2026-10-22T15:00:00'
    assert len(third.list()) == len(SAMPLE_LEADS) + 1
    third.dispose()


def test_new_process_reads_persisted_lead(tmp_path: Path) -> None:
    url = _url(tmp_path / 'leads.db')
    store = SqlLeadStore(url)
    created = store.create({'customer_name': 'Dana Ellis', 'phone': '+14695550110', 'status': 'new'})
    store.dispose()

    script = """
import json, sys
from app.db.store import SqlLeadStore
store = SqlLeadStore(sys.argv[1])
print(json.dumps(store.get(sys.argv[2])))
store.dispose()
"""
    result = subprocess.run(
        [sys.executable, '-c', script, url, created['id']],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded['customer_name'] == 'Dana Ellis'
    assert loaded['phone'] == '+14695550110'
