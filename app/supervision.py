"""Consent and human approvals with synthetic transport/calendar receipts only."""
from datetime import datetime, timezone, timedelta
import json
from uuid import uuid4
from app.controls.core import canonical, digest, WorkflowError, now
from app.security import services

SCHEMA='''
CREATE TABLE IF NOT EXISTS contact_permissions (
 tenant TEXT NOT NULL,recipient TEXT NOT NULL,purpose TEXT NOT NULL,
 active INTEGER NOT NULL,evidence TEXT NOT NULL,version INTEGER NOT NULL,
 PRIMARY KEY(tenant,recipient,purpose));
CREATE TABLE IF NOT EXISTS supervised_actions (
 tenant TEXT NOT NULL,id TEXT NOT NULL,lead TEXT NOT NULL,kind TEXT NOT NULL,
 requester TEXT NOT NULL,packet TEXT NOT NULL,packet_hash TEXT NOT NULL,
 state TEXT NOT NULL,expires TEXT NOT NULL,approver TEXT,
 result TEXT,created_at TEXT NOT NULL,PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS simulated_receipts (
 tenant TEXT NOT NULL,action TEXT NOT NULL,result TEXT NOT NULL,
 PRIMARY KEY(tenant,action));
CREATE TABLE IF NOT EXISTS simulated_visits (
 tenant TEXT NOT NULL,action TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,
 PRIMARY KEY(tenant,action));
'''


def setup(store):
    store.db.executescript(SCHEMA)


def lead_on(store,ctx,lead_id):
    row=store.db.execute('SELECT body FROM leads WHERE tenant=? AND id=?',(ctx.tenant,lead_id)).fetchone()
    if row is None:
        raise WorkflowError('Lead unavailable')
    return json.loads(row[0])


def update_lead(store,ctx,lead,updates):
    lead.update(updates)
    store.db.execute('UPDATE leads SET body=? WHERE tenant=? AND id=?',(canonical(lead),ctx.tenant,lead['id']))
    store.db.execute('INSERT INTO lead_audit(tenant,lead_id,kind,at) VALUES(?,?,?,?)',
                     (ctx.tenant,lead['id'],'lead.supervised_update',now().isoformat()))


def permission(store,ctx,recipient):
    row=store.db.execute('SELECT * FROM contact_permissions WHERE tenant=? AND recipient=? AND purpose=?',
                         (ctx.tenant,recipient,'service_sms')).fetchone()
    return dict(row) if row else None


def record_permission(ctx,lead_id,active,evidence):
    if ctx.role not in {'owner','dispatcher'}:
        raise WorkflowError('Intake permission required')
    if type(active) is not bool or not isinstance(evidence,str) or not evidence.strip():
        raise WorkflowError('Explicit permission state and evidence required')
    with services() as (store,_):
        setup(store)
        def op():
            lead=lead_on(store,ctx,lead_id)
            old=permission(store,ctx,lead['phone'])
            version=old['version']+1 if old else 1
            store.db.execute('INSERT INTO contact_permissions VALUES(?,?,?,?,?,?) ON CONFLICT(tenant,recipient,purpose) DO UPDATE SET active=excluded.active,evidence=excluded.evidence,version=excluded.version',
                              (ctx.tenant,lead['phone'],'service_sms',int(active),evidence,version))
            if not active:
                for row in store.db.execute('SELECT * FROM supervised_actions WHERE tenant=? AND kind=? AND state IN (?,?)',
                                             (ctx.tenant,'message','draft','approved')).fetchall():
                    if json.loads(row['packet'])['recipient']==lead['phone']:
                        store.db.execute('UPDATE supervised_actions SET state=? WHERE tenant=? AND id=?',('cancelled',ctx.tenant,row['id']))
            store._event(ctx,'consent.recorded',{'lead':lead_id,'active':active,'version':version,'purpose':'service_sms'})
            return {'active':active,'version':version}
        return store._transaction(op)


def propose(ctx,lead_id,kind,message=None):
    if ctx.role not in {'owner','dispatcher'} or kind not in {'message','booking'}:
        raise WorkflowError('Unsupported action or role')
    with services() as (store,_):
        setup(store)
        def op():
            lead=lead_on(store,ctx,lead_id)
            if lead.get('safety_hold') or lead['status'] in {'lost','completed','booking_confirmed_simulated'}:
                raise WorkflowError('Lead requires review or is closed/confirmed')
            packet={'lead_hash':digest(lead),'recipient':lead['phone'],'kind':kind,'lead':lead_id,'mode':'simulation','policy':'supervised-v1'}
            if kind=='message':
                grant=permission(store,ctx,lead['phone'])
                if not grant or not grant['active']:
                    raise WorkflowError('Current service SMS permission required')
                text=message or lead.get('follow_up_draft') or lead['recommended_reply']
                if not isinstance(text,str) or not 1<=len(text.strip())<=1600:
                    raise WorkflowError('Message must contain 1–1600 characters')
                packet.update(message=text,permission_version=grant['version'])
            else:
                if lead['status']!='booking_requested':
                    raise WorkflowError('Customer booking request required')
                start=datetime.fromisoformat(lead['appointment_time'].replace('Z','+00:00')).astimezone(timezone.utc)
                if start<=now():
                    raise WorkflowError('Future requested visit required')
                packet.update(start=start.isoformat(),end=(start+timedelta(hours=1)).isoformat(),calendar='synthetic-one-technician')
            pid=str(uuid4())
            store.db.execute('INSERT INTO supervised_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (ctx.tenant,pid,lead_id,kind,ctx.actor,canonical(packet),digest(packet),'draft',
                 (now()+timedelta(minutes=15)).isoformat(),None,None,now().isoformat()))
            store._event(ctx,'supervised.proposed',{'action':pid,'kind':kind,'lead':lead_id})
            return {'id':pid,'state':'draft'}
        return store._transaction(op)


def checked(store,ctx,pid):
    row=store.db.execute('SELECT * FROM supervised_actions WHERE tenant=? AND id=?',(ctx.tenant,pid)).fetchone()
    if row is None:
        raise WorkflowError('Action unavailable')
    action=dict(row);packet=json.loads(action['packet'])
    if digest(packet)!=action['packet_hash']:
        raise WorkflowError('Packet integrity failure')
    if now()>=datetime.fromisoformat(action['expires']):
        raise WorkflowError('Action expired; propose again')
    lead=lead_on(store,ctx,action['lead'])
    if digest(lead)!=packet['lead_hash']:
        raise WorkflowError('Lead changed; propose again')
    if lead.get('safety_hold') or lead['status'] in {'completed','lost'}:
        raise WorkflowError('Safety or lifecycle hold')
    if action['kind']=='message':
        grant=permission(store,ctx,packet['recipient'])
        if not grant or not grant['active'] or grant['version']!=packet['permission_version']:
            raise WorkflowError('Permission changed or revoked')
    return action,packet,lead


def approve(ctx,pid):
    if ctx.role!='owner':
        raise WorkflowError('Owner approval required')
    with services() as (store,_):
        setup(store)
        def op():
            action,packet,lead=checked(store,ctx,pid)
            if action['state']!='draft' or action['requester']==ctx.actor:
                raise WorkflowError('A different human must approve a draft')
            store.db.execute('UPDATE supervised_actions SET approver=?,state=? WHERE tenant=? AND id=?',
                             (ctx.actor,'approved',ctx.tenant,pid))
            store._event(ctx,'supervised.approved',{'action':pid,'packet_hash':action['packet_hash']})
            return {'state':'approved'}
        return store._transaction(op)


def finalize(store,ctx,lead,action,result):
    if action['kind']=='booking':
        update_lead(store,ctx,lead,{'status':'booking_confirmed_simulated','simulation_booking_ref':result['provider_reference']})
    else:
        update_lead(store,ctx,lead,{'last_simulated_message':now().isoformat()})


def execute(ctx,pid,scenario='success'):
    if ctx.role not in {'owner','dispatcher'} or scenario not in {'success','timeout_after_accept','reject'}:
        raise WorkflowError('Invalid executor or simulation scenario')
    with services() as (store,_):
        setup(store)
        def op():
            old=store.db.execute('SELECT * FROM supervised_actions WHERE tenant=? AND id=?',(ctx.tenant,pid)).fetchone()
            if old is None:
                raise WorkflowError('Action unavailable')
            if old['state']=='simulated_confirmed':
                return json.loads(old['result'])
            if old['state']=='unknown':
                raise WorkflowError('Outcome unknown; reconcile before any retry')
            action,packet,lead=checked(store,ctx,pid)
            if action['state']!='approved' or not action['approver']:
                raise WorkflowError('Exact human approval required')
            if action['kind']=='booking':
                if datetime.fromisoformat(packet['start'])<=now():
                    raise WorkflowError('Requested visit is in the past')
                conflict=store.db.execute('SELECT 1 FROM simulated_visits WHERE tenant=? AND start<? AND end>?',
                                          (ctx.tenant,packet['end'],packet['start'])).fetchone()
                if conflict:
                    raise WorkflowError('Simulated calendar slot no longer available')
            if scenario=='reject':
                result={'mode':'simulation','state':'rejected','reason':'Simulated provider rejection'}
                store.db.execute('UPDATE supervised_actions SET state=?,result=? WHERE tenant=? AND id=?',('rejected',canonical(result),ctx.tenant,pid))
                store._event(ctx,'supervised.rejected',{'action':pid})
                return result
            result={'mode':'simulation','state':'simulated_confirmed','provider_reference':'sim-'+pid,'kind':action['kind'],'accepted_at':now().isoformat()}
            store.db.execute('INSERT INTO simulated_receipts VALUES(?,?,?)',(ctx.tenant,pid,canonical(result)))
            if action['kind']=='booking':
                store.db.execute('INSERT INTO simulated_visits VALUES(?,?,?,?)',(ctx.tenant,pid,packet['start'],packet['end']))
            state='unknown' if scenario=='timeout_after_accept' else 'simulated_confirmed'
            store.db.execute('UPDATE supervised_actions SET state=?,result=? WHERE tenant=? AND id=?',
                             (state,canonical(result) if state!='unknown' else None,ctx.tenant,pid))
            if state!='unknown':
                finalize(store,ctx,lead,action,result)
            store._event(ctx,'supervised.'+state,{'action':pid,'kind':action['kind']})
            return {'mode':'simulation','state':'unknown'} if state=='unknown' else result
        return store._transaction(op)


def reconcile(ctx,pid):
    if ctx.role not in {'owner','dispatcher'}:
        raise WorkflowError('Intake permission required')
    with services() as (store,_):
        setup(store)
        def op():
            action=store.db.execute('SELECT * FROM supervised_actions WHERE tenant=? AND id=?',(ctx.tenant,pid)).fetchone()
            if not action or action['state']!='unknown':
                raise WorkflowError('Unknown action required')
            receipt=store.db.execute('SELECT result FROM simulated_receipts WHERE tenant=? AND action=?',(ctx.tenant,pid)).fetchone()
            if receipt is None:
                return {'state':'unknown','mode':'simulation'}
            result=json.loads(receipt['result'])
            lead=lead_on(store,ctx,action['lead'])
            # Reconcile observed acceptance even after opt-out; never resend it.
            if digest(lead)==json.loads(action['packet'])['lead_hash']:
                finalize(store,ctx,lead,dict(action),result)
            store.db.execute('UPDATE supervised_actions SET state=?,result=? WHERE tenant=? AND id=?',
                             ('simulated_confirmed',receipt['result'],ctx.tenant,pid))
            store._event(ctx,'supervised.reconciled',{'action':pid,'kind':action['kind']})
            return result
        return store._transaction(op)


def snapshot(ctx):
    with services() as (store,_):
        setup(store)
        actions=[dict(r) for r in store.db.execute('SELECT * FROM supervised_actions WHERE tenant=? ORDER BY created_at DESC',(ctx.tenant,))]
        permissions=[dict(r) for r in store.db.execute('SELECT * FROM contact_permissions WHERE tenant=?',(ctx.tenant,))]
        first_response={}
        for action in actions:
            if action['kind']=='message' and action['state']=='simulated_confirmed' and action['result']:
                accepted=json.loads(action['result']).get('accepted_at')
                if accepted:
                    prior=first_response.get(action['lead'])
                    first_response[action['lead']]=min(prior,accepted) if prior else accepted
        delays=[]
        for lid,accepted in first_response.items():
            lead=lead_on(store,ctx,lid)
            delays.append(max(0,(datetime.fromisoformat(accepted)-datetime.fromisoformat(lead['created_at'])).total_seconds()))
        return {'mode':'simulation','actions':actions,'permissions':permissions,
                'metrics':{'proposed':len(actions),'approved':sum(bool(a['approver']) for a in actions),
                           'simulated_confirmations':sum(a['state']=='simulated_confirmed' for a in actions),
                           'unknown_outcomes':sum(a['state']=='unknown' for a in actions),
                           'real_messages_sent':0,'real_appointments_confirmed':0,'staff_time_saved':None,
                           'real_response_seconds':None,
                           'simulation_first_response_seconds_mean':round(sum(delays)/len(delays),1) if delays else None}}
