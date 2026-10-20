from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from app.security import services

PAYLOAD={'customer_name':'Company A private fixture','phone':'2145550130','service_type':'cooling','property_type':'residential'}


def login(client,company='pilot-local',actor='owner'):
    response=client.post('/api/session',json={'actor':actor,'company_id':company})
    assert response.status_code==200,response.text


def create_lead(client):
    result=client.post('/api/leads',json=PAYLOAD)
    assert result.status_code==200
    return result.json()['id']


def test_two_company_lead_isolation_and_identity_tampering(client):
    login(client);aid=create_lead(client)
    login(client,'demo-gulf');bid=create_lead(client)
    assert {x['id'] for x in client.get('/api/leads').json()}=={bid}
    assert client.get(f'/api/leads/{aid}?company_id=pilot-local',headers={'X-Tenant':'pilot-local'}).status_code==404
    for suffix,payload in [('status',{'status':'contacted'}),('follow-up',{}),('review-request',{}),('book',{'appointment_time':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}),('handoff',{})]:
        assert client.post(f'/api/leads/{aid}/{suffix}',json=payload).status_code==404
    assert client.post('/api/operations',json={'action':'snapshot','parameters':{'tenant':'pilot-local'}}).status_code==409
    login(client)
    assert {x['id'] for x in client.get('/api/leads').json()}=={aid}


def test_finance_holds_and_events_are_company_scoped(client):
    login(client)
    def op(action,parameters):
        return client.post('/api/operations',json={'action':action,'parameters':parameters})
    assert op('create_job',{'job':'company-a-job'}).status_code==200
    assert op('submit_closeout',{'job':'company-a-job','evidence':['fixture-a']}).status_code==200
    pid=op('propose_invoice',{'job':'company-a-job','revenue':100,'direct_cost':50,'selling_cost':0,'tax':0}).json()['result']
    login(client,'demo-gulf','reviewer')
    assert op('approve',{'pid':pid}).status_code==409
    assert op('record_payment',{'invoice':'foreign-invoice','reference':'p','amount':1}).status_code==409
    workspace=client.get('/api/workspace').json()['operations']
    assert workspace['jobs']==workspace['invoices']==workspace['proposals']==[]
    assert not any('company-a-job' in e['payload'] for e in workspace['events'])
    login(client,'demo-gulf','quality')
    assert op('set_hold',{'job':'company-a-job','kind':'quality','reason':'cross-company attempt'}).status_code==409


def test_supervised_actions_and_consent_do_not_cross_companies(client):
    login(client);lid=create_lead(client)
    client.post('/api/supervision/consent',json={'lead_id':lid,'active':True,'evidence':'Fixture consent'})
    login(client,actor='dispatcher')
    pid=client.post('/api/supervision/propose',json={'lead_id':lid,'kind':'message'}).json()['id']
    login(client,'demo-gulf')
    result=client.get('/api/supervision').json()
    assert result['actions']==result['permissions']==[]
    assert client.post('/api/supervision/approve',json={'action_id':pid}).status_code==409
    assert client.post('/api/supervision/consent',json={'lead_id':lid,'active':False,'evidence':'Foreign request'}).status_code==409


def test_operator_metadata_access_does_not_grant_client_data(client):
    login(client);lid=create_lead(client)
    assert client.get('/api/platform/companies').status_code==401
    client.cookies.clear()
    assert client.post('/api/platform/session',json={}).status_code==200
    admin_token=client.cookies.get('jarvis_admin_session')
    assert client.get('/api/platform/companies').status_code==200
    assert client.get('/api/leads').status_code==401
    # Copying an operator cookie into the client slot must not create client rights.
    client.cookies.set('jarvis_session',admin_token)
    assert client.get(f'/api/leads/{lid}').status_code==401
    result=client.get('/api/platform/companies').json()
    assert 'Company A private fixture' not in str(result)
    assert result['client_data_access']=='not granted'


def test_operator_can_create_demo_company_and_pause_sessions(client):
    client.post('/api/platform/session',json={})
    response=client.post('/api/platform/companies',json={'name':'Demo · Third client','service_area':'Austin','calendar_provider':'google_calendar','messaging_provider':'twilio'})
    assert response.status_code==200,response.text
    cid=response.json()['id']
    assert response.json()['connections']=='not connected'
    login(client,cid)
    assert client.get('/api/leads').json()==[]
    token=client.cookies.get('jarvis_session')
    assert client.post(f'/api/platform/companies/{cid}/enabled',json={'enabled':False}).status_code==200
    assert client.get('/api/workspace').status_code==401
    assert client.post('/api/session',json={'actor':'owner','company_id':cid}).status_code==403
    client.post(f'/api/platform/companies/{cid}/enabled',json={'enabled':True})
    client.cookies.set('jarvis_session',token,domain='testserver.local',path='/')
    assert client.get('/api/workspace').status_code==401
    login(client,cid)
    assert client.get('/api/workspace').status_code==200


def test_client_cookie_cannot_be_used_for_operator_actions(client):
    login(client)
    token=client.cookies.get('jarvis_session')
    client.cookies.set('jarvis_admin_session',token)
    assert client.post('/api/platform/companies',json={'name':'Unauthorized','service_area':'DFW'}).status_code==401
    assert client.post('/api/platform/companies/pilot-local/enabled',json={'enabled':False}).status_code==401
    assert client.post('/api/session',json={'actor':'platform-demo','company_id':'__platform__'}).status_code==400


def test_assistant_memory_is_separate_for_same_staff_name(client,monkeypatch):
    import openai
    from app import assistant
    monkeypatch.setattr(assistant,'settings',SimpleNamespace(openai_api_key='fake',openai_model='fixture'))
    messages=[]
    class Fake:
        def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self)
        def create(self,**kwargs):
            messages.append(kwargs['messages'])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Fixture answer'))])
    monkeypatch.setattr(openai,'OpenAI',Fake)
    login(client)
    assert client.post('/api/assistant',json={'message':'Company A private question'}).status_code==200
    login(client,'demo-gulf')
    assert client.post('/api/assistant',json={'message':'Company B question'}).status_code==200
    assert len(messages[1])==2
    assert 'Company A private question' not in str(messages[1])
