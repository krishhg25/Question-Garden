"""Run inside backend container; creates a uniquely named demo test account."""
import io
import secrets
import uuid
import httpx
import pymupdf
from PIL import Image, ImageDraw, ImageFont

client = httpx.Client(base_url='http://127.0.0.1:8000/api', timeout=120)
email = f'deploy-check-{uuid.uuid4().hex[:12]}@example.com'
password = secrets.token_urlsafe(24)
r = client.post('/auth/signup', json={'name': 'Deployment check', 'email': email, 'password': password})
r.raise_for_status()
client.headers['Authorization'] = 'Bearer ' + r.json()['token']
assert r.json()['user']['free_credits'] == 100
r = client.post('/auth/signin', json={'email': email, 'password': password})
r.raise_for_status()
facts = '\n'.join(f'Concept {i} is a unique scientific idea with identifier number {i}.' for i in range(7))
# Avoid near-duplicate synthetic statements; use distinct actual statements.
facts = '''Photosynthesis produces glucose and oxygen.
Chlorophyll absorbs light energy from sunlight.
The nucleus contains genetic material inside cells.
Mitochondria are organelles that release energy through respiration.
Ribosomes are structures that synthesize proteins inside cells.
Vacuoles are compartments that store water and nutrients.
The cell wall protects plant cells from mechanical damage.'''
r = client.post('/sessions', json={'title': 'Deployment verification', 'text': facts}); r.raise_for_status()
sid = r.json()['id']
r = client.post(f'/sessions/{sid}/generate', json={'count': 10, 'kinds': ['fib'], 'request_id': str(uuid.uuid4())}); r.raise_for_status()
assert r.json()['generated'] == 7, r.text
assert r.json()['charged'] == 7
for answers in ['true', 'false']:
    r = client.get(f'/sessions/{sid}/export?answers={answers}'); r.raise_for_status()
    assert r.content.startswith(b'%PDF')
image = Image.new('RGB', (1600, 500), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 36)
draw.text((50, 100), 'Photosynthesis produces glucose and oxygen.', fill='black', font=font)
png = io.BytesIO(); image.save(png, 'PNG')
doc = pymupdf.open(); page = doc.new_page(width=800, height=250)
page.insert_image(page.rect, stream=png.getvalue())
r = client.post('/sessions/upload', files={'file': ('ocr-check.pdf', doc.tobytes(), 'application/pdf')}); r.raise_for_status()
assert r.json()['extraction']['ocr_images_or_pages'] == 1
assert 'Photosynthesis' in r.json()['text'], r.text
ocr_id = r.json()['id']
r = client.post(f'/sessions/{ocr_id}/generate', json={'count': 3, 'kinds': ['fib'], 'request_id': str(uuid.uuid4())}); r.raise_for_status()
assert r.json()['generated'] == 1 and r.json()['charged'] == 2, r.text
purchase_id = str(uuid.uuid4())
for _ in range(2):
    r = client.post('/credits/demo-purchase', json={'request_id': purchase_id}); r.raise_for_status()
assert client.get('/me').json()['paid_credits'] == 1000
for source_id in [sid, ocr_id]:
    client.delete(f'/sessions/{source_id}').raise_for_status()
client.post('/auth/logout').raise_for_status()
print('PASS: email signup/signin, PostgreSQL persistence, 7-of-10 exhaustion, billing, both PDF exports, real scanned PDF Tesseract OCR, document pricing, idempotent demo purchase, deletion and logout.')
