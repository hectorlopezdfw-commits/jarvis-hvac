from pathlib import Path
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.api.routes import router
from app.pilot_api import router as pilot_router
from app.assistant import router as assistant_router
from app.supervised_api import router as supervised_router
from app.config import settings
from app.controls import WorkflowError
from app.db.in_memory_store import scope
from app.security import bootstrap, services


@asynccontextmanager
async def lifespan(app):
    if settings.app_env=='production':
        raise RuntimeError('Production launch requires verified identity and connector controls; local pilot only.')
    bootstrap()
    yield


app=FastAPI(title=settings.app_name,version='0.2.0',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])


@app.middleware('http')
async def boundary(request: Request, call_next):
    if request.url.hostname not in {'127.0.0.1','localhost','testserver'}:
        return JSONResponse({'detail':'Invalid host'},status_code=400)
    origin=request.headers.get('origin')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        expected=str(request.base_url).rstrip('/')
        if origin!=expected or request.headers.get('x-jarvis-request')!='1':
            return JSONResponse({'detail':'Same-origin application request required'},status_code=403)
        try:
            if int(request.headers.get('content-length','0'))>32768:
                return JSONResponse({'detail':'Request too large'},status_code=413)
        except ValueError:
            return JSONResponse({'detail':'Invalid request size'},status_code=400)
    public={'/api/session','/api/sales-offer','/api/sales-pitch'}
    token=None
    if request.url.path.startswith('/api/') and request.url.path not in public:
        try:
            with services() as (_, access):
                ctx=access.resolve(request.cookies.get('jarvis_session',''))
            request.state.ctx=ctx
            # Existing lead mutations belong to intake/dispatch roles.
            if request.method=='POST' and (request.url.path.startswith('/api/leads') or request.url.path=='/api/ai/qualify') and ctx.role not in {'owner','dispatcher'}:
                return JSONResponse({'detail':'Intake or dispatch permission required'},status_code=403)
            token=scope.set(ctx.tenant)
        except WorkflowError:
            return JSONResponse({'detail':'Start a local pilot session'},status_code=401)
    try:
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response
    finally:
        if token is not None:
            scope.reset(token)


app.include_router(router)
app.include_router(pilot_router)
app.include_router(assistant_router)
app.include_router(supervised_router)
static_dir=Path(__file__).resolve().parent.parent/'static'
app.mount('/static',StaticFiles(directory=str(static_dir)),name='static')


@app.get('/health')
def health_check():
    return {'status':'ok','app':settings.app_name,'environment':settings.app_env,'mode':'local pilot'}


@app.get('/')
def serve_demo():
    return FileResponse(static_dir/'index.html')


@app.get('/sales')
def serve_sales_page():
    return FileResponse(static_dir/'landing.html')
