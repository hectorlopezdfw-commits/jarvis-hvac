from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool
from app.controls import WorkflowError
from app import supervision

router=APIRouter(prefix='/api/supervision')


def invoke(fn,*args):
    try:
        return fn(*args)
    except (WorkflowError,ValueError) as error:
        raise HTTPException(409,str(error)) from error


class Consent(BaseModel):
    lead_id: str
    active: StrictBool
    evidence: str=Field(min_length=1,max_length=2000)


class Proposal(BaseModel):
    lead_id: str
    kind: str
    message: str | None=Field(default=None,max_length=1600)


class Action(BaseModel):
    action_id: str


class Execution(Action):
    scenario: str='success'


@router.get('')
def snapshot(request: Request):
    if request.state.ctx.role not in {'owner','dispatcher'}:
        raise HTTPException(403,'Intake permission required')
    return invoke(supervision.snapshot,request.state.ctx)


@router.post('/consent')
def consent(payload: Consent,request: Request):
    return invoke(supervision.record_permission,request.state.ctx,payload.lead_id,payload.active,payload.evidence)


@router.post('/propose')
def propose(payload: Proposal,request: Request):
    return invoke(supervision.propose,request.state.ctx,payload.lead_id,payload.kind,payload.message)


@router.post('/approve')
def approve(payload: Action,request: Request):
    return invoke(supervision.approve,request.state.ctx,payload.action_id)


@router.post('/execute')
def execute(payload: Execution,request: Request):
    return invoke(supervision.execute,request.state.ctx,payload.action_id,payload.scenario)


@router.post('/reconcile')
def reconcile(payload: Action,request: Request):
    return invoke(supervision.reconcile,request.state.ctx,payload.action_id)
