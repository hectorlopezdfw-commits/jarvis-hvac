"""Operator metadata plane. Does not provide access to a client's lead records."""
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictBool
from typing import Literal
from app.controls import WorkflowError
from app.security import services, STAFF

router=APIRouter(prefix='/api')


@router.get('/companies')
def demo_companies():
    with services() as (store,_):
        return [dict(r) for r in store.db.execute('SELECT id,name FROM companies WHERE enabled=1 AND demo=1 ORDER BY name')]


@router.post('/platform/session')
def platform_session(request: Request,response: Response):
    # Local simulated operator only. Production startup remains blocked.
    with services() as (_,access):
        old=request.cookies.get('jarvis_admin_session')
        if old:
            try:
                access.revoke(old)
            except WorkflowError:
                pass
        token=access.issue('__platform__','platform-demo',3600)
    response.set_cookie('jarvis_admin_session',token,httponly=True,samesite='strict',max_age=3600)
    return {'mode':'operator simulation; no production identity','role':'platform_admin'}


@router.post('/platform/logout')
def logout(request: Request,response: Response):
    with services() as (_,access):
        access.revoke(request.cookies.get('jarvis_admin_session',''))
    response.delete_cookie('jarvis_admin_session')
    return {'ok':True}


@router.get('/platform/companies')
def companies(request: Request):
    with services() as (store,_):
        records=[dict(r) for r in store.db.execute('SELECT * FROM companies ORDER BY name')]
    return {'companies':records,'mode':'demo onboarding only','client_data_access':'not granted',
            'production_identity':'not configured','provider_connections':'not configured'}


class Company(BaseModel):
    name: str=Field(min_length=2,max_length=120)
    service_area: str=Field(min_length=2,max_length=120)
    timezone: str='America/Chicago'
    messaging_provider: Literal['undecided','twilio']='undecided'
    calendar_provider: Literal['undecided','google_calendar']='undecided'


@router.post('/platform/companies')
def create_company(payload: Company,request: Request):
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError,ValueError):
        raise HTTPException(422,'Valid IANA timezone required')
    if not payload.name.strip() or not payload.service_area.strip():
        raise HTTPException(422,'Company name and service area required')
    cid='demo-'+uuid4().hex[:16]
    with services() as (store,access):
        def op():
            store.db.execute('INSERT INTO companies VALUES(?,?,?,?,?,?,1,1)',
                 (cid,payload.name.strip(),payload.service_area.strip(),payload.timezone,payload.messaging_provider,payload.calendar_provider))
            for actor,role in STAFF.items():
                store.db.execute('INSERT INTO memberships VALUES(?,?,?,1)',(cid,actor,role))
            store._event(request.state.ctx,'company.created',{'company_id':cid,'demo':True})
        store._transaction(op)

    return {'id':cid,'name':payload.name.strip(),'mode':'demo','connections':'not connected'}


class Enabled(BaseModel):
    enabled: StrictBool


@router.post('/platform/companies/{company_id}/enabled')
def toggle(company_id: str,payload: Enabled,request: Request):
    with services() as (store,_):
        def op():
            if not store.db.execute('SELECT 1 FROM companies WHERE id=?',(company_id,)).fetchone():
                raise HTTPException(404,'Company unavailable')
            store.db.execute('UPDATE companies SET enabled=? WHERE id=?',(int(payload.enabled),company_id))
            if not payload.enabled:
                store.db.execute('UPDATE sessions SET revoked=1 WHERE tenant=?',(company_id,))
            store._event(request.state.ctx,'company.enabled_changed',{'company_id':company_id,'enabled':payload.enabled})
        store._transaction(op)
    return {'enabled':payload.enabled}
