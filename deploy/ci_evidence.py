"""Produce repeatable evidence using real libraries, OCR and an isolated test API."""
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ci-results'
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / 'backend'))
FACTS = '''Photosynthesis is the process that converts sunlight into chemical energy.
Chlorophyll is the green pigment that absorbs sunlight in plants.
The nucleus is the organelle that contains genetic material.
The cell membrane is the barrier that controls entry and exit of substances.
Photosynthesis requires sunlight, water, and carbon dioxide.
Photosynthesis produces glucose and oxygen.
Photosynthesis occurs in the chloroplasts of plant cells.'''

def main():
    with tempfile.TemporaryDirectory(prefix='question-garden-ci-') as temp:
        os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(temp)/'isolated.db').replace('\\','/')
        os.environ['ALLOW_DEMO_AUTH'] = 'false'
        os.environ['OLLAMA_URL'] = ''
        import pymupdf as fitz
        import pytesseract
        from docx import Document
        from fastapi.testclient import TestClient
        from app.documents import extract_document
        from app.generator import build_graph
        from app.main import app
        from app.database import engine

        results = {'captured_at_utc': datetime.now(timezone.utc).isoformat(),
                   'python': platform.python_version(), 'platform': platform.platform(),
                   'packages': {p:version(p) for p in ['fastapi','SQLAlchemy','pytest','PyMuPDF','python-docx','pytesseract','nltk','networkx','reportlab','psycopg']}}
        results['tesseract'] = str(pytesseract.get_tesseract_version())
        with fitz.open() as native:
            page = native.new_page()
            page.insert_textbox(fitz.Rect(40,40,550,790), FACTS, fontsize=14)
            pdf = native.tobytes()
            text, meta = extract_document('source.pdf', pdf)
            assert 'Photosynthesis' in text
            results['native_pdf'] = meta
            pix = page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            with fitz.open() as scan:
                image_page=scan.new_page()
                image_page.insert_image(image_page.rect,stream=pix.tobytes('png'))
                assert not image_page.get_text().strip()
                image_pdf=scan.tobytes()
        text,meta=extract_document('scan.pdf',image_pdf)
        assert meta['ocr_images_or_pages']==1 and 'Photosynthesis' in text
        results['real_scanned_pdf_ocr']=meta
        doc=Document()
        for line in FACTS.splitlines(): doc.add_paragraph(line)
        buf=io.BytesIO();doc.save(buf)
        word_text,meta=extract_document('source.docx',buf.getvalue())
        assert 'Chlorophyll' in word_text
        results['docx']=meta
        graph=build_graph(FACTS)
        assert graph['fact_count']==7
        results['nlp_graph']={'engine':graph['engine'],'facts':graph['fact_count'],'nodes':len(graph['nodes']),'edges':len(graph['edges'])}
        with TestClient(app) as client:
            health=client.get('/api/health');assert health.status_code==200
            results['api_health']={'status':health.status_code,'body':health.json(),'database':'isolated SQLite (not PostgreSQL)'}
        # Only store package/runtime details and synthetic test results, never secrets.
        (OUT/'tool-evidence.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        (OUT/'ocr-extracted-text.txt').write_text(text,encoding='utf-8')
        (OUT/'scan-input.pdf').write_bytes(image_pdf)
        print(json.dumps(results,indent=2))
        print('PASS: real OCR, PDF, DOCX, NLP/NetworkX and FastAPI health checks')
        engine.dispose()

if __name__=='__main__':main()
