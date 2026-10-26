# Verification record

Checked locally on 16 October 2026.

- Backend: **17 tests passed** with Python 3.14.2 and SQLite. Includes seven-from-ten exhaustion, all four formats, source-evidence coverage, fact reuse prevention, mixed-format graph traversal, generation/purchase idempotency, conflicting retry IDs, daily reset, purchased-credit carryover, free-first spending, insufficient credits, simultaneous spending, account isolation, logout, DOCX/PDF extraction, original downloads, both PDF export modes, malformed uploads, empty generation, deletion including cached results, mocked Google-token verification, and Ollama failure fallback.
- Frontend: **production build passed** with Vite 7.3.7. Installation audit reported zero vulnerabilities at installation time; this is not a permanent security guarantee.
- Browser: local demo sign-in, sample text generation, all four formats in a mixed set, saved graph, source-linked answers, a simulated purchase adding 1,000 credits, saved sessions, and the questions-and-answers PDF download worked.
- Responsive check: at a 390 px viewport, the page had no horizontal overflow and session navigation remained available.
- Deployment YAML parsed successfully. Python 3.12 cross-platform dependency resolution completed and was saved in `backend/requirements.lock`.

Not verified locally: live Google OAuth (no client ID supplied), real Tesseract execution (not installed on this Windows host), Ollama inference (no model server supplied), PostgreSQL runtime, Docker/Linux container startup, public TLS, or a cloud deployment. Docker is not installed on this host. The OCR test checks routing with a mocked OCR result; it does not claim to test recognition accuracy. The CI template includes both SQLite and a disposable PostgreSQL run. Follow the Ubuntu guide's acceptance checks on the VM.

One dependency deprecation warning is emitted by the installed Starlette TestClient integration with httpx. It does not cause the tests to fail.

The running local preview uses the shared development-only demo user and contains sample biology sessions plus a simulated purchase made during testing. Google-authenticated production accounts are separate and start with the daily allowance.
