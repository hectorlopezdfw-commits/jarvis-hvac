from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import sqlite3
import pytest
from app.db.in_memory_store import InMemoryLeadStore, scope

PAYLOAD={'customer_name':'Synthetic Demo','phone':'2145550100','service_type':'cooling',
         'property_type':'residential','emergency':False,'notes':'Synthetic request'}


def create(owner):
    result=owner.post('/api/leads',json=PAYLOAD)
    assert result.status_code==200, result.text
    return result.json()['id']


def test_health_and_sales(client):
    assert client.get('/health').status_code==200
    assert 'pricing' in client.get('/api/sales-offer').json()
    assert client.get('/sales').status_code==200


def test_requires_session_and_origin(client):
    assert client.get('/api/leads').status_code==401
    assert client.post('/api/session',json={'actor':'owner'},headers={'Origin':'https://attacker.invalid'}).status_code==403
    assert client.get('/api/leads',headers={'host':'attacker.invalid'}).status_code==400


def test_lead_capture_and_draft_do_not_fake_contact(owner):
    lead=create(owner)
    response=owner.post(f'/api/leads/{lead}/follow-up',json={'channel':'sms'})
    assert response.status_code==200
    assert response.json()['result']['status']=='draft'
    record=owner.get(f'/api/leads/{lead}').json()
    assert record['status']=='new'
    assert record['follow_up_draft']


def test_booking_requests_not_confirmations(owner):
    lead=create(owner)
    assert owner.post(f'/api/leads/{lead}/book',json={'appointment_time':'2020-01-01T12:00:00Z'}).status_code==409
    assert owner.post(f'/api/leads/{lead}/book',json={'appointment_time':'2030-01-01T12:00:00'}).status_code==409
    future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    record=owner.post(f'/api/leads/{lead}/book',json={'appointment_time':future}).json()
    assert record['status']=='booking_requested'
    assert owner.get('/api/dashboard').json()['booked_leads']==0


def test_review_completion_gate_and_lifecycle(owner):
    lead=create(owner)
    assert owner.post(f'/api/leads/{lead}/review-request',json={}).status_code==409
    assert owner.post(f'/api/leads/{lead}/status',json={'status':'completed'}).status_code==409
    future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    owner.post(f'/api/leads/{lead}/book',json={'appointment_time':future})
    assert owner.post(f'/api/leads/{lead}/status',json={'status':'completed'}).status_code==200
    assert owner.post(f'/api/leads/{lead}/review-request',json={}).status_code==200
    assert owner.get(f'/api/leads/{lead}').json()['status']=='completed'


def test_hazard_holds_routine_work(owner):
    payload={**PAYLOAD,'notes':'Smell gas and a CO alarm'}
    record=owner.post('/api/leads',json=payload).json()
    assert record['safety_hold'] is True
    lead=record['id']
    future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    assert owner.post(f'/api/leads/{lead}/book',json={'appointment_time':future}).status_code==409
    assert owner.post(f'/api/leads/{lead}/follow-up',json={}).status_code==409


def test_linked_lead_to_cash_with_separate_roles(owner):
    lead=create(owner)
    assert owner.post(f'/api/leads/{lead}/handoff').status_code==409
    future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    owner.post(f'/api/leads/{lead}/book',json={'appointment_time':future})
    owner.post(f'/api/leads/{lead}/status',json={'status':'completed'})
    job=owner.post(f'/api/leads/{lead}/handoff').json()['job_id']
    assert owner.post(f'/api/leads/{lead}/handoff').json()['job_id']==job
    def op(action,parameters):
        return owner.post('/api/operations',json={'action':action,'parameters':parameters})
    assert op('submit_closeout',{'job':job,'evidence':['synthetic-photo']}).status_code==200
    pid=op('propose_invoice',{'job':job,'revenue':100000,'direct_cost':60000,'selling_cost':5000,'tax':0}).json()['result']
    assert op('execute_invoice',{'pid':pid}).status_code==409
    owner.post('/api/session',json={'actor':'reviewer'})
    assert owner.post('/api/leads',json=PAYLOAD).status_code==403
    assert op('approve',{'pid':pid}).status_code==200
    owner.post('/api/session',json={'actor':'finance'})
    invoice=op('execute_invoice',{'pid':pid}).json()['result']
    for _ in range(10):
        assert op('execute_invoice',{'pid':pid}).json()['result']['id']==invoice['id']
    owner.post('/api/session',json={'actor':'reviewer'})
    assert op('record_payment',{'invoice':invoice['id'],'reference':'synthetic-p1','amount':100000}).status_code==200
    workspace=owner.get('/api/workspace').json()['operations']
    assert workspace['jobs'][0]['state']=='paid'
    assert len(workspace['invoices'])==1


def test_tenant_persistence_and_scope(tmp_path,monkeypatch):
    monkeypatch.setenv('JARVIS_DB',str(tmp_path/'leads.sqlite'))
    token=scope.set('tenant-a')
    try:
        first=InMemoryLeadStore(); record=first.create(PAYLOAD)
        assert InMemoryLeadStore().get(record['id'])['customer_name']=='Synthetic Demo'
        scope.set('tenant-b')
        assert InMemoryLeadStore().get(record['id']) is None
        assert InMemoryLeadStore().list()==[]
    finally:
        scope.reset(token)
    with pytest.raises(ValueError):
        InMemoryLeadStore().list()


def test_logout_revokes_session(owner):
    cookie=owner.cookies.get('jarvis_session')
    assert owner.post('/api/logout').status_code==200
    assert owner.get('/api/leads',headers={'Cookie':f'jarvis_session={cookie}'}).status_code==401


def test_assistant_is_read_only_and_remembers(owner,monkeypatch):
    import openai
    from app import assistant
    monkeypatch.setattr(assistant,'settings',SimpleNamespace(openai_api_key='test-not-a-real-key',openai_model='fixture'))
    captured=[]
    class Fake:
        def __init__(self,**kwargs):
            self.chat=SimpleNamespace(completions=self)
        def create(self,**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Review new leads first.'))])
    monkeypatch.setattr(openai,'OpenAI',Fake)
    before=owner.get('/api/workspace').json()['operations']
    assert owner.post('/api/assistant',json={'message':'What needs attention?'}).status_code==200
    assert owner.post('/api/assistant',json={'message':'What next?'}).status_code==200
    assert len(captured[1]['messages'])==4
    assert 'tools' not in captured[0]
    after=owner.get('/api/workspace').json()['operations']
    assert before['jobs']==after['jobs'] and before['invoices']==after['invoices']
    owner.post('/api/session',json={'actor':'finance'})
    assert owner.post('/api/assistant',json={'message':'Hi'}).status_code==403
