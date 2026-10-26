import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite:///./test_question_generator.db')
os.environ['ALLOW_DEMO_AUTH'] = 'true'
os.environ['OLLAMA_URL'] = ''

import pymupdf as fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.database import Base, Operation, Question, Session, User, engine
from app.generator import build_graph, candidates, extract_facts, key
from app.main import app, rate_buckets, start_login, today
from app import documents
from app import main

FACTS = '''Photosynthesis is the process that converts sunlight into chemical energy.
Chlorophyll is the green pigment that absorbs sunlight in plants.
The nucleus is the organelle that contains genetic material.
The cell membrane is the barrier that controls entry and exit of substances.
Photosynthesis requires sunlight, water, and carbon dioxide.
Photosynthesis produces glucose and oxygen.
Photosynthesis occurs in the chloroplasts of plant cells.'''


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    rate_buckets.clear()
    with TestClient(app) as client:
        yield client


def auth(client):
    result = client.post('/api/auth/demo')
    assert result.status_code == 200
    return {'Authorization': 'Bearer ' + result.json()['token']}


def source(client, headers, text=FACTS):
    result = client.post('/api/sessions', headers=headers, json={'title': 'Plant biology', 'text': text})
    assert result.status_code == 201, result.text
    return result.json()['id']


def generate(client, headers, source_id, count=10, kinds=None, request_id=None):
    return client.post(f'/api/sessions/{source_id}/generate', headers=headers,
                       json={'count': count, 'kinds': kinds or ['fib'], 'request_id': request_id or str(uuid4())})


def test_exhaustion_and_billing(client):
    headers = auth(client)
    sid = source(client, headers)
    result = generate(client, headers, sid).json()
    assert result['generated'] == 7
    assert result['charged'] == 7
    assert result['reason'] == 'source_exhausted'
    assert result['user']['free_credits'] == 93
    again = generate(client, headers, sid).json()
    assert again['generated'] == 0 and again['charged'] == 0
    assert again['user']['free_credits'] == 93


def test_all_formats_and_long_answer_consumption(client):
    for kind in ['mcq', 'fib', 'short', 'long']:
        headers = auth(client)
        sid = source(client, headers)
        response = generate(client, headers, sid, kinds=[kind]).json()
        assert response['generated'] > 0, kind
        for question in response['questions']:
            assert question['kind'] == kind
            assert all(e in FACTS for e in question['evidence'])
            if kind == 'mcq':
                assert len(set(question['options'])) == 4
                assert question['answer'] in question['options']
            if kind == 'long':
                assert len(question['evidence']) >= 3
        if kind == 'long':
            used = {e for q in response['questions'] for e in q['evidence']}
            more = generate(client, headers, sid, kinds=['short']).json()
            assert not used.intersection(e for q in more['questions'] for e in q['evidence'])


def test_generation_retry_and_conflict(client):
    headers = auth(client)
    sid = source(client, headers)
    rid = str(uuid4())
    first = generate(client, headers, sid, count=2, request_id=rid)
    second = generate(client, headers, sid, count=2, request_id=rid)
    assert first.json() == second.json()
    assert client.get('/api/me', headers=headers).json()['free_credits'] == 98
    assert generate(client, headers, sid, count=3, request_id=rid).status_code == 409


def test_purchase_retry_and_daily_reset(client):
    headers = auth(client)
    rid = str(uuid4())
    for _ in range(2):
        result = client.post('/api/credits/demo-purchase', headers=headers, json={'request_id': rid})
        assert result.json()['simulated'] is True
    with Session.begin() as db:
        user = db.scalar(select(User))
        user.free_credits = 8
        user.reset_date = today() - timedelta(days=1)
    profile = client.get('/api/me', headers=headers).json()
    assert profile['free_credits'] == 100
    assert profile['paid_credits'] == 1000
    assert profile['timezone'] == 'Asia/Kolkata'


def test_credit_limit_and_free_before_purchased(client):
    headers = auth(client)
    sid = source(client, headers)
    with Session.begin() as db:
        user = db.scalar(select(User))
        user.free_credits, user.paid_credits = 1, 2
    result = generate(client, headers, sid).json()
    assert result['generated'] == 3 and result['charged'] == 3
    assert result['reason'] == 'credit_limit'
    assert result['user']['total_credits'] == 0
    assert generate(client, headers, sid).status_code == 402


def test_account_isolation_and_logout(client):
    headers = auth(client)
    sid = source(client, headers)
    other = start_login('another-google-sub', 'another@example.test', 'Another')
    foreign = {'Authorization': 'Bearer ' + other['token']}
    assert client.get('/api/sessions', headers=foreign).json() == []
    for suffix in ['', '/original', '/export']:
        assert client.get(f'/api/sessions/{sid}{suffix}', headers=foreign).status_code == 404
    assert generate(client, foreign, sid).status_code == 404
    assert client.delete(f'/api/sessions/{sid}', headers=foreign).status_code == 404
    assert client.get('/api/sessions').status_code == 401
    assert client.post('/api/auth/logout', headers=headers).status_code == 200
    assert client.get('/api/me', headers=headers).status_code == 401


def test_docx_upload_original_and_double_cost(client):
    headers = auth(client)
    document = Document()
    document.add_paragraph(FACTS)
    buffer = io.BytesIO()
    document.save(buffer)
    data = buffer.getvalue()
    response = client.post('/api/sessions/upload', headers=headers, files={'file': ('biology.docx', data)})
    assert response.status_code == 201, response.text
    sid = response.json()['id']
    assert client.get(f'/api/sessions/{sid}/original', headers=headers).content == data
    result = generate(client, headers, sid).json()
    assert result['generated'] == 7 and result['charged'] == 14
    assert result['user']['free_credits'] == 86


def test_pdf_extraction_and_export_modes(client):
    headers = auth(client)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 550, 750), FACTS, fontsize=11)
    response = client.post('/api/sessions/upload', headers=headers, files={'file': ('biology.pdf', doc.tobytes())})
    assert response.status_code == 201, response.text
    sid = response.json()['id']
    assert response.json()['extraction']['ocr_images_or_pages'] == 0
    generate(client, headers, sid, count=2)
    for answers in [False, True]:
        export = client.get(f'/api/sessions/{sid}/export?answers={str(answers).lower()}', headers=headers)
        assert export.status_code == 200 and export.content.startswith(b'%PDF')
        with fitz.open(stream=export.content, filetype='pdf') as output:
            text = ''.join(page.get_text() for page in output)
            assert ('Answer:' in text) == answers


def test_scan_routes_through_ocr(client, monkeypatch):
    monkeypatch.setattr(documents, 'ocr', lambda image: FACTS)
    doc = fitz.open()
    page = doc.new_page()
    buffer = io.BytesIO()
    Image.new('RGB', (600, 800), 'white').save(buffer, 'PNG')
    page.insert_image(page.rect, stream=buffer.getvalue())
    text, info = documents.extract_document('scan.pdf', doc.tobytes())
    assert text == FACTS and info['ocr_images_or_pages'] == 1


def test_invalid_documents_and_generation_validation(client):
    headers = auth(client)
    assert client.post('/api/sessions/upload', headers=headers, files={'file': ('broken.pdf', b'not-pdf')}).status_code == 422
    assert client.post('/api/sessions/upload', headers=headers, files={'file': ('old.doc', b'old')}).status_code == 422
    sid = source(client, headers)
    assert generate(client, headers, sid, count=51).status_code == 422
    assert client.post(f'/api/sessions/{sid}/generate', headers=headers,
                       json={'count': 5, 'kinds': [], 'request_id': str(uuid4())}).status_code == 422


def test_no_facts_no_charge_and_delete(client):
    headers = auth(client)
    sid = source(client, headers, text='A random heading without any factual assertions or extractable relationships.')
    result = generate(client, headers, sid).json()
    assert result['generated'] == result['charged'] == 0
    assert result['user']['total_credits'] == 100
    assert client.delete(f'/api/sessions/{sid}', headers=headers).status_code == 200
    assert client.get(f'/api/sessions/{sid}', headers=headers).status_code == 404


def test_concurrent_generation_cannot_double_spend(client):
    headers = auth(client)
    sid = source(client, headers)
    with Session.begin() as db:
        db.scalar(select(User)).free_credits = 3
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: generate(client, headers, sid, count=3), range(2)))
    assert sorted(r.status_code for r in results) == [200, 402]
    assert client.get('/api/me', headers=headers).json()['total_credits'] == 0
    assert len(client.get(f'/api/sessions/{sid}', headers=headers).json()['questions']) == 3


def test_duplicates_and_graph():
    assert len(extract_facts(FACTS + '\n' + FACTS)) == 7
    graph = build_graph(FACTS)
    assert graph['fact_count'] == 7 and len(graph['edges']) == 7
    assert candidates('The cat is a friendly pet animal.', set(), ['mcq']) == []
    assert candidates('The cat is a friendly pet animal.', set(), ['long']) == []


def test_email_auth(client):
    body = {'name': 'Learner', 'email': 'Learner@example.com', 'password': 'test-password-12345'}
    result = client.post('/api/auth/signup', json=body)
    assert result.status_code == 201
    assert result.json()['user']['free_credits'] == 100
    assert client.post('/api/auth/signup', json=body).status_code == 409
    assert client.post('/api/auth/signin', json={**body, 'email': 'learner@example.com'}).status_code == 200
    assert client.post('/api/auth/signin', json={**body, 'password': 'wrong-password'}).status_code == 401
    assert client.post('/api/auth/signin', json={**body, 'email': 'missing@example.com'}).status_code == 401
    assert client.post('/api/auth/signup', json={**body, 'password': 'short'}).status_code == 422
    assert client.post('/api/auth/google', json={}).status_code == 404


def test_deletion_removes_cached_question_content(client):
    headers = auth(client)
    sid = source(client, headers)
    generate(client, headers, sid)
    client.delete(f'/api/sessions/{sid}', headers=headers)
    with Session() as db:
        assert not db.scalars(select(Operation)).all()
        assert not db.scalars(select(Question)).all()


def test_mixed_types_use_graph_group_without_losing_facts():
    result = candidates(FACTS, set(), ['mcq', 'fib', 'short', 'long'])
    assert {q['kind'] for q in result} == {'mcq', 'fib', 'short', 'long'}
    assert len({fid for q in result for fid in q['fact_ids']}) == 7


def test_ollama_failure_falls_back_without_changing_answers(monkeypatch):
    import httpx
    from app import generator
    monkeypatch.setattr(main.settings, 'ollama_url', 'http://unused.test')
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(generator.httpx, 'post', unavailable)
    original = candidates(FACTS, set(), ['fib'])
    rewritten, engine_name = generator.improve_wording(original)
    assert rewritten == original
    assert 'unavailable' in engine_name
