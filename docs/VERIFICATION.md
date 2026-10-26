# Verification record — 26 October 2026

## Executed Jenkins CI

- Repository: https://github.com/krishhg25/Question-Garden
- Build: **#3 — SUCCESS**, checked-out commit `c16aa78f768a5e99044d7fc6558b0a3591e8f60c`.
- Duration: 340.664 seconds.
- Backend: **17 passed**, 0 failed, 0 skipped, using isolated SQLite.
- Frontend: npm clean install and Vite production build passed.
- Actual OCR: Tesseract processed a generated image-only PDF; native PDF and DOCX extraction also passed.
- NLP/graph: seven source facts produced eleven nodes and seven edges.
- API: FastAPI health check returned HTTP 200.
- Docker: both `question-garden-backend:ci-3` and `question-garden-frontend:ci-3` built successfully on the Docker Desktop Linux engine.
- Evidence: Jenkins published JUnit test results and archived runtime details, OCR input/output, frontend build output and Jenkinsfile.

Build #1 passed with Docker explicitly disabled. Build #2 was stopped after Debian HTTP package download failures; the Dockerfile was fixed to use HTTPS with retries and strict package-index checking. Build #3 used that fix.

The pipeline is CI only: it does not push images to a registry, deploy to GCP, run Ansible, or provision infrastructure. One Starlette/httpx deprecation warning remains. The unit-test OCR-routing case uses a mock; the separate CI OCR stage runs the real binary.

## Historical deployment and remaining boundaries

The 16 October 2026 Ubuntu/GCP deployment is documented in `deploy/LIVE_VM.md`. The owner reports that the cloud trial expired; current cloud availability is not asserted. Ansible, Terraform, Prometheus, Grafana and related tools remain proposed integrations. GitHub Actions is only an unactivated template. Backup scheduling/restoration and public TLS are not verified by Jenkins.

The current app uses email/password authentication with salted scrypt hashes; Google OAuth is no longer used. Optional Ollama inference is not demonstrated. Screenshots and original build records are kept in the local report evidence folder; the report labels missing screenshots rather than inventing them.

## Local Compose runtime verified

After build #3, the images ran in a separate `question-garden-evidence` Compose project. PostgreSQL, backend and frontend health checks passed; Caddy served the website and API on `127.0.0.1:8085`. The synthetic end-to-end test passed email signup/signin, PostgreSQL persistence, seven-from-ten generation, exact billing, both PDF export modes, real scanned-PDF OCR, document pricing, idempotent demo purchase, deletion and logout.

The demonstration uses a separate PostgreSQL volume and localhost-only port binding. It is not a public or GCP deployment. Version, health and smoke-test logs are preserved in the local report's `evidence/compose/` directory.
