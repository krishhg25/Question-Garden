import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import re
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import Base, Ledger, Login, Operation, Question, Session, Source, User, PasswordCredential, engine, now, transaction
from .documents import export_pdf, extract_document
from .generator import build_graph, candidates, improve_wording, key

logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title='Question Garden API', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=[x.strip() for x in settings.cors_origins.split(',')],
                   allow_methods=['GET', 'POST', 'DELETE'],
                   allow_headers=['Authorization', 'Content-Type'])

# Single-process coarse abuse protection; nginx also enforces shared per-IP limits.
rate_lock = Lock()
rate_buckets = {}


@app.middleware('http')
async def headers_and_limits(request: Request, call_next):
    if request.method == 'POST':
        address = request.client.host if request.client else 'unknown'
        bearer = request.headers.get('authorization', '')
        if bearer.startswith('Bearer '):
            address = hashlib.sha256(bearer.encode()).hexdigest()
        minute = int(time.monotonic() // 60)
        with rate_lock:
            for old in [k for k in rate_buckets if k[1] != minute]:
                del rate_buckets[old]
            bucket = (address, minute)
            rate_buckets[bucket] = rate_buckets.get(bucket, 0) + 1
            exceeded = rate_buckets[bucket] > 60
        if exceeded:
            return Response('Too many requests. Try again in a minute.', status_code=429)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


def today():
    return datetime.now(ZoneInfo(settings.credit_timezone)).date()


def iso_utc(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def refresh_credits(db, user):
    day = today()
    if user.reset_date < day:
        user.free_credits = 100
        user.reset_date = day
        db.add(Ledger(user_id=user.id, amount=100, reason='Daily free allowance reset (unused free credits expire)'))


def user_view(user):
    tz = ZoneInfo(settings.credit_timezone)
    next_reset = datetime.combine(today() + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return {'id': user.id, 'name': user.name, 'email': user.email,
            'free_credits': user.free_credits, 'paid_credits': user.paid_credits,
            'total_credits': user.free_credits + user.paid_credits,
            'next_reset': next_reset.isoformat(), 'timezone': settings.credit_timezone}


def identity(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Please sign in to continue.')
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with Session() as db:
        login = db.get(Login, token_hash)
        if not login or login.expires.replace(tzinfo=timezone.utc) <= now():
            raise HTTPException(401, 'Your session expired. Please sign in again.')
        return login.user_id


def locked_user(db, user_id):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(401, 'Account not found.')
    refresh_credits(db, user)
    return user


def owned_source(db, source_id, user_id):
    source = db.scalar(select(Source).where(Source.id == source_id, Source.user_id == user_id))
    if not source:
        raise HTTPException(404, 'Session not found.')
    return source


def source_view(db, source, full=False):
    questions = db.scalars(select(Question).where(Question.source_id == source.id).order_by(Question.created_at, Question.id)).all()
    result = {'id': source.id, 'title': source.title, 'kind': source.kind, 'filename': source.filename,
              'created_at': iso_utc(source.created_at), 'question_count': len(questions),
              'fact_count': source.graph['fact_count'], 'extraction': source.extraction}
    if full:
        result.update(text=source.text, graph=source.graph, questions=[question_view(q) for q in questions])
    return result


def question_view(q):
    return {'id': q.id, 'kind': q.kind, 'prompt': q.prompt, 'answer': q.answer,
            'options': q.options, 'evidence': q.evidence}


def start_login(sub, email, name):
    # Retry a simultaneous first sign-in after the unique Google subject constraint wins.
    for attempt in range(2):
        try:
            with transaction() as db:
                user = db.scalar(select(User).where(User.google_sub == sub).with_for_update())
                if not user:
                    user = User(google_sub=sub, email=email, name=name[:200], reset_date=today())
                    db.add(user)
                    db.flush()
                    db.add(Ledger(user_id=user.id, amount=100, reason='Welcome daily free allowance'))
                refresh_credits(db, user)
                token = secrets.token_urlsafe(48)
                db.execute(delete(Login).where(Login.expires < now()))
                db.add(Login(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                             expires=now() + timedelta(days=7)))
                return {'token': token, 'user': user_view(user)}
        except IntegrityError:
            if attempt:
                raise


@app.get('/api/health')
def health():
    with Session() as db:
        db.execute(text('SELECT 1'))
    return {'status': 'ok'}


@app.get('/api/config')
def config():
    return {'auth_method': 'email', 'demo_auth': settings.allow_demo_auth,
            'demo_payments': settings.demo_payments_enabled, 'max_upload_mb': settings.max_upload_mb,
            'max_pages': settings.max_pages, 'max_text_chars': settings.max_text_chars,
            'engine': 'NLP + knowledge graph' + (' + Ollama' if settings.ollama_url else ''),
            'credit_timezone': settings.credit_timezone}


class EmailLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class EmailSignup(EmailLogin):
    name: str = Field(min_length=1, max_length=100)


def normalize_email(email):
    email = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, 'Enter a valid email address.')
    return email


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1,
                          maxmem=64 * 1024 * 1024).hex()


def issue_login(db, user):
    refresh_credits(db, user)
    token = secrets.token_urlsafe(48)
    db.add(Login(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                 expires=now() + timedelta(days=7)))
    return {'token': token, 'user': user_view(user)}


@app.post('/api/auth/signup', status_code=201)
def signup(body: EmailSignup):
    email = normalize_email(body.email)
    if not body.name.strip():
        raise HTTPException(422, 'Enter your name.')
    salt = secrets.token_hex(16)
    hashed = password_hash(body.password, salt)
    try:
        with transaction() as db:
            if db.get(PasswordCredential, email):
                raise HTTPException(409, 'An account with this email already exists. Sign in instead.')
            user = User(google_sub='email:' + hashlib.sha256(email.encode()).hexdigest(),
                        email=email, name=body.name.strip(), reset_date=today())
            db.add(user)
            db.flush()
            db.add(PasswordCredential(email=email, user_id=user.id, salt=salt, password_hash=hashed))
            db.add(Ledger(user_id=user.id, amount=100, reason='Welcome daily free allowance'))
            return issue_login(db, user)
    except IntegrityError:
        raise HTTPException(409, 'An account with this email already exists. Sign in instead.')


@app.post('/api/auth/signin')
def signin(body: EmailLogin):
    email = normalize_email(body.email)
    with transaction() as db:
        credential = db.get(PasswordCredential, email)
        salt = credential.salt if credential else '00' * 16
        candidate = password_hash(body.password, salt)
        if not credential or not secrets.compare_digest(candidate, credential.password_hash):
            raise HTTPException(401, 'Invalid email or password.')
        return issue_login(db, locked_user(db, credential.user_id))


@app.post('/api/auth/demo')
def demo_login():
    if not settings.allow_demo_auth:
        raise HTTPException(404, 'Demo sign-in is disabled.')
    return start_login('local-demo', 'demo@localhost', 'Demo learner')


@app.post('/api/auth/logout')
def logout(user_id=Depends(identity), authorization: str = Header(default='')):
    with transaction() as db:
        db.execute(delete(Login).where(Login.token_hash == hashlib.sha256(authorization[7:].encode()).hexdigest()))
    return {'ok': True}


@app.get('/api/me')
def me(user_id=Depends(identity)):
    with transaction() as db:
        return user_view(locked_user(db, user_id))


@app.get('/api/ledger')
def ledger(user_id=Depends(identity)):
    with Session() as db:
        rows = db.scalars(select(Ledger).where(Ledger.user_id == user_id).order_by(Ledger.created_at.desc()).limit(100)).all()
        return [{'id': row.id, 'amount': row.amount, 'reason': row.reason, 'created_at': iso_utc(row.created_at)} for row in rows]


class TextSource(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20, max_length=60000)


@app.post('/api/sessions', status_code=201)
def create_text(body: TextSource, user_id=Depends(identity)):
    if len(body.text.strip()) < 20 or not body.title.strip():
        raise HTTPException(422, 'Enter a title and at least 20 characters of source text.')
    if len(body.text) > settings.max_text_chars:
        raise HTTPException(413, 'Source text exceeds the configured limit.')
    with transaction() as db:
        source = Source(user_id=user_id, title=body.title.strip(), text=body.text.strip(), kind='text',
                        graph=build_graph(body.text), extraction={'characters': len(body.text), 'ocr_images_or_pages': 0})
        db.add(source)
        db.flush()
        return source_view(db, source, True)


@app.post('/api/sessions/upload', status_code=201)
def upload(file: UploadFile = File(...), user_id=Depends(identity)):
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f'Upload a file smaller than {settings.max_upload_mb} MB.')
    filename = (file.filename or 'document').replace('\\', '/').split('/')[-1][:255]
    try:
        content, extraction = extract_document(filename, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with transaction() as db:
        source = Source(user_id=user_id, title=filename[:200], kind='document', text=content,
                        filename=filename, original=data, graph=build_graph(content), extraction=extraction)
        db.add(source)
        db.flush()
        return source_view(db, source, True)


@app.get('/api/sessions')
def sessions(user_id=Depends(identity)):
    with Session() as db:
        rows = db.scalars(select(Source).where(Source.user_id == user_id).order_by(Source.created_at.desc())).all()
        return [source_view(db, row) for row in rows]


@app.get('/api/sessions/{source_id}')
def session_detail(source_id: str, user_id=Depends(identity)):
    with Session() as db:
        return source_view(db, owned_source(db, source_id, user_id), True)


@app.delete('/api/sessions/{source_id}')
def remove_session(source_id: str, user_id=Depends(identity)):
    with transaction() as db:
        locked_user(db, user_id)
        source = owned_source(db, source_id, user_id)
        db.execute(delete(Question).where(Question.source_id == source.id))
        db.execute(delete(Operation).where(Operation.user_id == user_id,
                                           Operation.result['source_id'].as_string() == source.id))
        db.delete(source)
    return {'ok': True}


@app.get('/api/sessions/{source_id}/original')
def original(source_id: str, user_id=Depends(identity)):
    with Session() as db:
        source = owned_source(db, source_id, user_id)
        data = source.original if source.original is not None else source.text.encode()
        extension = '.txt' if source.kind == 'text' else ('.pdf' if source.filename.lower().endswith('.pdf') else '.docx')
        return Response(data, media_type='application/octet-stream',
                        headers={'Content-Disposition': f'attachment; filename="source{extension}"'})


class GenerateRequest(BaseModel):
    count: int = Field(ge=1, le=50)
    kinds: list[Literal['mcq', 'fib', 'short', 'long']] = Field(min_length=1, max_length=4)
    request_id: UUID


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def existing_operation(db, user_id, request_id, digest):
    operation = db.scalar(select(Operation).where(Operation.user_id == user_id, Operation.key == str(request_id)))
    if operation and operation.fingerprint != digest:
        raise HTTPException(409, 'This request ID was already used for a different operation.')
    return operation.result if operation else None


@app.post('/api/sessions/{source_id}/generate')
def generate(source_id: str, body: GenerateRequest, user_id=Depends(identity)):
    digest = fingerprint({'source': source_id, 'count': body.count, 'kinds': body.kinds})
    # Serialize per-account writes, including generation retries and purchases.
    with transaction() as db:
        user = locked_user(db, user_id)
        source = owned_source(db, source_id, user_id)
        previous = existing_operation(db, user_id, body.request_id, digest)
        if previous is not None:
            return previous
        old = db.scalars(select(Question).where(Question.source_id == source.id)).all()
        used = {key(evidence) for q in old for evidence in q.evidence}
        cost = 1 if source.kind == 'text' else 2
        available = (user.free_credits + user.paid_credits) // cost
        if available == 0:
            raise HTTPException(402, 'You do not have enough credits. Wait for the daily reset or add demo credits.')
        pool = candidates(source.text, used, list(dict.fromkeys(body.kinds)), [q.prompt for q in old])
        selected, engine_name = improve_wording(pool[:min(body.count, available)])
        saved = []
        for item in selected:
            question = Question(source_id=source.id, **{k: v for k, v in item.items() if k != 'fact_ids'})
            db.add(question)
            saved.append(question)
        db.flush()
        charged = len(saved) * cost
        free_charge = min(charged, user.free_credits)
        user.free_credits -= free_charge
        user.paid_credits -= charged - free_charge
        if charged:
            db.add(Ledger(user_id=user_id, amount=-charged, reason=f'{len(saved)} questions from {source.kind}: {source.title[:140]}'))
        if len(saved) == body.count:
            reason = 'requested_count_reached'
            message = f'Generated {len(saved)} questions. Charged {charged} credits.'
        elif len(pool) <= len(saved):
            reason = 'source_exhausted'
            message = f'Generated {len(saved)} of {body.count}. No more supported, unused facts fit the selected formats. Charged only {charged} credits.'
        else:
            reason = 'credit_limit'
            message = f'Generated {len(saved)} of {body.count} within your credit balance. Charged {charged} credits.'
        result = {'source_id': source.id, 'questions': [question_view(q) for q in saved], 'generated': len(saved),
                  'requested': body.count, 'charged': charged, 'reason': reason, 'message': message,
                  'engine': engine_name, 'user': user_view(user)}
        db.add(Operation(user_id=user_id, key=str(body.request_id), fingerprint=digest, result=result))
        return result


class Purchase(BaseModel):
    request_id: UUID


@app.post('/api/credits/demo-purchase')
def purchase(body: Purchase, user_id=Depends(identity)):
    if not settings.demo_payments_enabled:
        raise HTTPException(404, 'Demo purchases are disabled.')
    digest = fingerprint({'product': 'demo-1000-credits-inr-100'})
    with transaction() as db:
        user = locked_user(db, user_id)
        previous = existing_operation(db, user_id, body.request_id, digest)
        if previous is not None:
            return previous
        user.paid_credits += 1000
        db.add(Ledger(user_id=user_id, amount=1000, reason='Demo payment: INR 100 simulated; no money charged'))
        result = {'message': 'Demo payment complete. 1,000 credits added. No money was charged.',
                  'credits_added': 1000, 'amount_inr': 100, 'simulated': True, 'user': user_view(user)}
        db.add(Operation(user_id=user_id, key=str(body.request_id), fingerprint=digest, result=result))
        return result


@app.get('/api/sessions/{source_id}/export')
def export(source_id: str, answers: bool = False, user_id=Depends(identity)):
    with Session() as db:
        source = owned_source(db, source_id, user_id)
        questions = db.scalars(select(Question).where(Question.source_id == source.id).order_by(Question.created_at, Question.id)).all()
        if not questions:
            raise HTTPException(422, 'Generate some questions before exporting.')
        return Response(export_pdf(source.title, questions, answers), media_type='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename="questions' + ('-and-answers' if answers else '') + '.pdf"'})
