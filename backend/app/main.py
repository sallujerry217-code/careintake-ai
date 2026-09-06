import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import FastAPI, Depends, Header, Request, Query, Body
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select, func, text, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException
from .config import settings
from .db import Base, engine, get_db
from .models import Patient, CallRecord, now
from .schemas import PatientInput, phone, dob
from .services import DomainError, get_patient, create_patient, update_patient, output
from .voice import handle_tools, end_report, validation_details

cfg = settings()
class JsonFormatter(logging.Formatter):
    def format(self, record):
        item = {'timestamp': now().isoformat(), 'level': record.levelname, 'event': record.getMessage()}
        for key in ('request_id', 'method', 'path', 'status', 'duration_ms', 'patient_id', 'payload'):
            if hasattr(record, key):
                item[key] = getattr(record, key)
        return json.dumps(item)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger('careintake')
logger.handlers = [handler]
logger.setLevel(cfg.log_level)
logger.propagate = False

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title='CareIntake AI', version='1.0.0', description='Voice patient registration demo. Use fictional data only.', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in cfg.cors_origins.split(',') if x.strip()], allow_methods=['GET','POST','PUT','DELETE'], allow_headers=['Authorization','Content-Type'], expose_headers=['X-Request-ID'])

def ok(data):
    return {'data': data, 'error': None}

def error(status, code, message, details=None):
    return JSONResponse(status_code=status, content={'data': None, 'error': {'code': code, 'message': message, 'details': details}})

@app.middleware('http')
async def request_context(request, call_next):
    request_id, started = str(uuid4()), time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.error('request.failed', extra={'request_id': request_id})
        response = error(500, 'INTERNAL_ERROR', 'A temporary system error occurred.')
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    logger.info('request.completed', extra={'request_id': request_id, 'method': request.method, 'path': request.url.path, 'status': response.status_code, 'duration_ms': round((time.monotonic()-started)*1000)})
    return response

@app.exception_handler(DomainError)
async def domain_error(_, exc):
    return error(exc.status, exc.code, exc.message, exc.details)

@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_, exc):
    return error(422, 'VALIDATION_ERROR', 'Please correct the indicated fields.', validation_details(exc))

@app.exception_handler(HTTPException)
async def http_error(_, exc):
    return error(exc.status_code, 'HTTP_ERROR', str(exc.detail))

@app.exception_handler(IntegrityError)
async def integrity_error(_, exc):
    return error(409, 'CONFLICT', 'This operation conflicts with an existing record or database constraint.')

@app.exception_handler(SQLAlchemyError)
async def database_error(_, exc):
    logger.error('database.operation_failed')
    return error(503, 'DATABASE_UNAVAILABLE', 'The database is temporarily unavailable. Please try again.')

def admin(authorization: str = Header(default='')):
    if cfg.admin_api_key and not secrets.compare_digest(authorization, 'Bearer '+cfg.admin_api_key):
        raise DomainError(401, 'UNAUTHORIZED', 'Enter a valid reviewer access key.')

def webhook_auth(x_vapi_secret: str = Header(default='')):
    if not cfg.vapi_secret or not secrets.compare_digest(x_vapi_secret, cfg.vapi_secret):
        raise DomainError(401, 'UNAUTHORIZED', 'Invalid webhook credentials.')

@app.get('/health')
def health(db=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return ok({'status':'healthy', 'database':'connected', 'version':'1.0.0'})

@app.get('/config')
def public_config():
    return ok({'auth_required':bool(cfg.admin_api_key), 'phone_number':cfg.phone_number, 'assistant_configured':bool(cfg.vapi_assistant_id), 'environment':cfg.app_env})

@app.get('/patients', dependencies=[Depends(admin)])
def list_patients(last_name: str | None = None, date_of_birth: str | None = None, phone_number: str | None = None, q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db)):
    stmt = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        stmt = stmt.where(func.lower(Patient.last_name) == last_name.strip().lower())
    if date_of_birth:
        try:
            parsed = date.fromisoformat(str(dob(date_of_birth)))
        except ValueError:
            raise DomainError(422, 'VALIDATION_ERROR', 'Use MM/DD/YYYY or YYYY-MM-DD for date_of_birth.')
        stmt = stmt.where(Patient.date_of_birth == parsed)
    if phone_number:
        try:
            number = phone(phone_number)
        except ValueError as e:
            raise DomainError(422, 'VALIDATION_ERROR', str(e))
        stmt = stmt.where(Patient.phone_number == number)
    if q:
        escaped = q.strip().replace('\\', '\\\\').replace('%','\\%').replace('_','\\_')
        stmt = stmt.where(or_(Patient.first_name.ilike('%'+escaped+'%', escape='\\'), Patient.last_name.ilike('%'+escaped+'%', escape='\\'), Patient.phone_number.ilike('%'+escaped+'%', escape='\\')))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    patients = db.scalars(stmt.order_by(Patient.created_at.desc()).offset(offset).limit(limit)).all()
    return {**ok([output(p) for p in patients]), 'meta': {'total':total, 'limit':limit, 'offset':offset}}

@app.get('/patients/search/by-phone', dependencies=[Depends(admin)])
def search_phone(phone_number: str, db=Depends(get_db)):
    return list_patients(phone_number=phone_number, q=None, limit=100, offset=0, db=db)

@app.get('/patients/{patient_id}', dependencies=[Depends(admin)])
def read_patient(patient_id: UUID, db=Depends(get_db)):
    return ok(output(get_patient(db, patient_id)))

@app.post('/patients', status_code=201, dependencies=[Depends(admin)])
def post_patient(data: PatientInput, db=Depends(get_db)):
    p = create_patient(db, data)
    db.commit()
    return ok(output(p))

@app.put('/patients/{patient_id}', dependencies=[Depends(admin)])
def put_patient(patient_id: UUID, changes: dict = Body(...), db=Depends(get_db)):
    p = update_patient(db, str(patient_id), changes)
    db.commit()
    return ok(output(p))

@app.delete('/patients/{patient_id}', dependencies=[Depends(admin)])
def delete_patient(patient_id: UUID, db=Depends(get_db)):
    p = get_patient(db, patient_id)
    p.deleted_at = p.updated_at = now()
    db.commit()
    return ok({'patient_id':p.patient_id, 'deleted_at':p.deleted_at.isoformat()})


def serialize_call(c, detail=False):
    data = {key: getattr(c,key) for key in ['call_id','provider_call_id','patient_id','caller_phone','started_at','ended_at','status','summary','created_at']}
    for key, value in data.items():
        if isinstance(value, datetime) and value.tzinfo is None:
            data[key] = value.replace(tzinfo=timezone.utc)
    if detail:
        data['transcript'] = c.transcript
    return data

@app.get('/calls', dependencies=[Depends(admin)])
def list_calls(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db=Depends(get_db)):
    rows = db.scalars(select(CallRecord).order_by(CallRecord.started_at.desc()).offset(offset).limit(limit)).all()
    return {**ok([serialize_call(c) for c in rows]), 'meta':{'total':db.scalar(select(func.count()).select_from(CallRecord))}}

@app.get('/calls/{call_id}', dependencies=[Depends(admin)])
def get_call(call_id: UUID, db=Depends(get_db)):
    c = db.get(CallRecord, str(call_id))
    if not c:
        raise DomainError(404, 'NOT_FOUND', 'Call not found.')
    return ok(serialize_call(c, True))

@app.get('/stats', dependencies=[Depends(admin)])
def stats(db=Depends(get_db)):
    active = Patient.deleted_at.is_(None)
    total = db.scalar(select(func.count()).select_from(Patient).where(active))
    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.scalar(select(func.count()).select_from(Patient).where(active, Patient.created_at >= midnight))
    calls = db.scalar(select(func.count()).select_from(CallRecord))
    registered = db.scalar(select(func.count()).select_from(CallRecord).where(CallRecord.patient_id.is_not(None)))
    return ok({'total_patients':total, 'registered_today':today, 'total_calls':calls, 'registered_calls':registered, 'registration_rate': round(100*registered/calls) if calls else None})

@app.post('/webhooks/vapi', dependencies=[Depends(webhook_auth)])
def vapi_webhook(payload: dict, db=Depends(get_db)):
    message = payload.get('message')
    if not isinstance(message, dict):
        raise DomainError(422, 'INVALID_WEBHOOK', 'Expected a Vapi message object.')
    if message.get('type') == 'tool-calls':
        return handle_tools(db, message)
    if message.get('type') == 'end-of-call-report':
        return end_report(db, message)
    return ok({'received':True, 'ignored':True})

static = Path(cfg.static_dir)
if static.exists():
    app.mount('/assets', StaticFiles(directory=static/'assets'), name='assets')
    @app.get('/', include_in_schema=False)
    def dashboard():
        return FileResponse(static/'index.html')
