from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from app.controls import WorkflowError
from app.controls.access import Gateway
from app.db.in_memory_store import lead_store
from app.security import services, STAFF

router = APIRouter(prefix='/api')


class SessionRequest(BaseModel):
    actor: str
    company_id: str="pilot-local"


@router.post('/session')
def session(payload: SessionRequest, request: Request, response: Response):
    if payload.actor not in STAFF:
        raise HTTPException(400,'Unknown pilot staff')
    with services() as (store, access):
        company=store.db.execute('SELECT * FROM companies WHERE id=? AND enabled=1 AND demo=1',(payload.company_id,)).fetchone()
        if company is None:
            raise HTTPException(403,'Demo company unavailable')
        old = request.cookies.get('jarvis_session')
        if old:
            try:
                access.revoke(old)
            except WorkflowError:
                pass
        token = access.issue(payload.company_id,payload.actor,3600)
    response.set_cookie('jarvis_session',token,httponly=True,samesite='strict',max_age=3600)
    return {'actor':payload.actor,'company_id':payload.company_id,'role':STAFF[payload.actor], 'mode':'local pilot; simulated identity'}


@router.post('/logout')
def logout(request: Request, response: Response):
    with services() as (_,access):
        access.revoke(request.cookies.get('jarvis_session',''))
    response.delete_cookie('jarvis_session')
    return {'ok':True}


@router.get('/workspace')
def workspace(request: Request):
    with services() as (store,_):
        data = store.snapshot(request.state.ctx)
        company=dict(store.db.execute('SELECT * FROM companies WHERE id=?',(request.state.ctx.tenant,)).fetchone())
    return {'actor':request.state.ctx.actor,'role':request.state.ctx.role,'company':company,'operations':data,
            'mode':'local pilot','messaging':'drafts only','scheduler':'requests only',
            'ai':'available on request; no autonomous actions'}


class Transition(BaseModel):
    status: str


@router.post('/leads/{lead_id}/status')
def transition(lead_id: str, payload: Transition, request: Request):
    if request.state.ctx.role not in {'owner','dispatcher'}:
        raise HTTPException(403,'Dispatch role required')
    lead = lead_store.get(lead_id)
    if not lead:
        raise HTTPException(404,'Lead not found')
    allowed = {'new':{'contacted','lost'},'contacted':{'lost'},'booking_requested':{'lost'},'booking_confirmed_simulated':{'completed','lost'}}
    if payload.status not in allowed.get(lead['status'],set()):
        raise HTTPException(409,'Invalid lifecycle transition')
    return lead_store.update(lead_id,{'status':payload.status})


@router.post('/leads/{lead_id}/handoff')
def handoff(lead_id: str, request: Request):
    if request.state.ctx.role!='owner':
        raise HTTPException(403,'Owner role required')
    lead = lead_store.get(lead_id)
    if not lead:
        raise HTTPException(404,'Lead not found')
    if lead['status']!='completed':
        raise HTTPException(409,'Completed service required before job handoff')
    job = 'job-'+lead_id
    with services() as (store,_):
        # Business idempotency: same tenant + lead always maps to one job.
        try:
            existing=store._job(request.state.ctx,job)
        except WorkflowError:
            store.create_job(request.state.ctx,job)
    lead_store.update(lead_id,{'job_id':job})
    return {'job_id':job}


class Operation(BaseModel):
    action: str
    parameters: dict = Field(default_factory=dict)


@router.post('/operations')
def operation(payload: Operation, request: Request):
    with services() as (_,access):
        try:
            return {'result':Gateway(access).call(request.cookies.get('jarvis_session',''),payload.action,payload.parameters)}
        except (WorkflowError, ValueError):
            raise HTTPException(409,'Operation blocked: check role, source version, evidence, approvals and holds')
