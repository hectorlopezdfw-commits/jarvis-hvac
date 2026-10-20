from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from app.controls import Context, WorkflowError
from app.security import services
from app import supervision

PAYLOAD={'customer_name':'Synthetic Pilot','phone':'2145550199','service_type':'cooling','property_type':'residential'}


def lead(client):
    return client.post('/api/leads',json=PAYLOAD).json()['id']


def consent(client,lid,active=True):
    return client.post('/api/supervision/consent',json={'lead_id':lid,'active':active,'evidence':'Synthetic evidence: explicit service SMS permission at intake.'})


def propose(client,lid,kind='message'):
    client.post('/api/session',json={'actor':'dispatcher'})
    response=client.post('/api/supervision/propose',json={'lead_id':lid,'kind':kind})
    assert response.status_code==200,response.text
    return response.json()['id']


def approve(client,pid):
    client.post('/api/session',json={'actor':'owner'})
    response=client.post('/api/supervision/approve',json={'action_id':pid})
    assert response.status_code==200,response.text


def test_permission_and_independent_human_approval(owner):
    lid=lead(owner)
    assert owner.post('/api/supervision/propose',json={'lead_id':lid,'kind':'message'}).status_code==409
    assert consent(owner,lid).status_code==200
    own=owner.post('/api/supervision/propose',json={'lead_id':lid,'kind':'message'}).json()['id']
    assert owner.post('/api/supervision/approve',json={'action_id':own}).status_code==409
    pid=propose(owner,lid)
    assert owner.post('/api/supervision/approve',json={'action_id':pid}).status_code==409
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409
    approve(owner,pid)
    response=owner.post('/api/supervision/execute',json={'action_id':pid})
    assert response.status_code==200 and response.json()['mode']=='simulation'
    assert owner.get(f'/api/leads/{lid}').json()['status']=='new'
    metrics=owner.get('/api/supervision').json()['metrics']
    assert metrics['simulation_first_response_seconds_mean']>=0
    assert metrics['real_response_seconds'] is None


def test_optout_cancels_queued_actions_for_same_contact(owner):
    lid=lead(owner);other=lead(owner)
    consent(owner,lid)
    pid=propose(owner,lid);approve(owner,pid)
    consent(owner,other,False)
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409
    actions=owner.get('/api/supervision').json()['actions']
    assert next(x for x in actions if x['id']==pid)['state']=='cancelled'
    assert owner.post('/api/supervision/propose',json={'lead_id':other,'kind':'message'}).status_code==409


def test_changed_lead_or_permission_invalidates_approval(owner):
    lid=lead(owner);consent(owner,lid)
    pid=propose(owner,lid);approve(owner,pid)
    owner.post(f'/api/leads/{lid}/status',json={'status':'contacted'})
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409
    pid=propose(owner,lid);approve(owner,pid)
    consent(owner,lid,True)  # New evidence version also invalidates the packet.
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409


def test_expiry_and_packet_integrity(owner):
    lid=lead(owner);consent(owner,lid)
    pid=propose(owner,lid);approve(owner,pid)
    with services() as (store,_):
        store.db.execute("UPDATE supervised_actions SET expires='2000-01-01T00:00:00+00:00' WHERE id=?",(pid,))
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409
    pid=propose(owner,lid)
    with services() as (store,_):
        store.db.execute("UPDATE supervised_actions SET packet='{}' WHERE id=?",(pid,))
    owner.post('/api/session',json={'actor':'owner'})
    assert owner.post('/api/supervision/approve',json={'action_id':pid}).status_code==409


def test_unknown_outcome_requires_reconciliation_even_after_optout(owner):
    lid=lead(owner);consent(owner,lid)
    pid=propose(owner,lid);approve(owner,pid)
    response=owner.post('/api/supervision/execute',json={'action_id':pid,'scenario':'timeout_after_accept'})
    assert response.json()['state']=='unknown'
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409
    consent(owner,lid,False)
    response=owner.post('/api/supervision/reconcile',json={'action_id':pid})
    assert response.json()['state']=='simulated_confirmed'
    for _ in range(10):
        assert owner.post('/api/supervision/execute',json={'action_id':pid}).json()['provider_reference']==response.json()['provider_reference']
    with services() as (store,_):
        assert store.db.execute('SELECT COUNT(*) FROM simulated_receipts').fetchone()[0]==1


def test_calendar_confirmation_before_completion_and_no_overlap(owner):
    future=(datetime.now(timezone.utc)+timedelta(days=1)).replace(microsecond=0).isoformat()
    ids=[]
    for _ in range(2):
        lid=lead(owner);ids.append(lid)
        assert owner.post(f'/api/leads/{lid}/book',json={'appointment_time':future}).status_code==200
    assert owner.post(f'/api/leads/{ids[0]}/status',json={'status':'completed'}).status_code==409
    actions=[]
    for lid in ids:
        pid=propose(owner,lid,'booking');approve(owner,pid);actions.append(pid)
    ctx=Context('pilot-local','owner','owner')
    def attempt(pid):
        try:
            return supervision.execute(ctx,pid)['state']
        except WorkflowError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,actions))
    assert sorted(results)==['blocked','simulated_confirmed']
    records=owner.get('/api/leads').json()
    confirmed=next(r for r in records if r['status']=='booking_confirmed_simulated')
    assert owner.post(f"/api/leads/{confirmed['id']}/status",json={'status':'completed'}).status_code==200


def test_rejection_and_metrics_never_claim_real_delivery(owner):
    lid=lead(owner);consent(owner,lid)
    pid=propose(owner,lid);approve(owner,pid)
    assert owner.post('/api/supervision/execute',json={'action_id':pid,'scenario':'reject'}).json()['state']=='rejected'
    assert owner.post('/api/supervision/execute',json={'action_id':pid}).status_code==409
    m=owner.get('/api/supervision').json()['metrics']
    assert m['real_messages_sent']==m['real_appointments_confirmed']==0
    assert m['staff_time_saved'] is None


def test_role_and_tenant_boundaries(owner):
    lid=lead(owner);consent(owner,lid)
    pid=propose(owner,lid);approve(owner,pid)
    with pytest.raises(WorkflowError):
        supervision.execute(Context('other','owner','owner'),pid)
    owner.post('/api/session',json={'actor':'finance'})
    assert owner.get('/api/supervision').status_code==403
    assert owner.post('/api/supervision/approve',json={'action_id':pid}).status_code==409
