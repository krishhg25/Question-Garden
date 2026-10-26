# Jenkins CI

Repository: https://github.com/krishhg25/Question-Garden

Create a **Pipeline** job, select **Pipeline script from SCM**, Git, this repository,
branch `*/main`, and script path `Jenkinsfile`. Public read access needs no GitHub
credentials. Jenkins only reads the repository; it does not push code or deploy to GCP.

The agent needs Python 3.12+, Node.js 22.12+, Git, and Tesseract with English data.
On Windows, put Python, Node, Git and Tesseract on the agent's PATH, or set
`TESSERACT_CMD` to the full OCR executable path. Run Jenkins on Java 21 or a version
supported by the installed Jenkins release. Keep the local demonstration bound to
127.0.0.1, with authentication enabled.

## Stages and evidence

1. Checkout: retrieve the repository revision and Jenkinsfile.
2. Install dependencies: create an isolated Python environment from the lockfile;
   install frontend dependencies with `npm ci`.
3. Backend tests: execute pytest and publish its JUnit XML results.
4. Frontend build: compile the React/Vite application.
5. OCR and API evidence: extract a native PDF and DOCX, OCR a synthetic image-only
   PDF using real Tesseract, build a knowledge graph, and check FastAPI health with
   an isolated SQLite database.
6. Docker image build: enable `BUILD_CONTAINERS` to build both application images.
   Docker Desktop must have a running Linux engine on Windows. If disabled, this
   stage is explicitly skipped. A successful image build does not prove deployment.
7. Archive evidence: publish frontend build output, the Jenkinsfile, the JUnit
   report, extracted OCR text, scanned input, and runtime version evidence.

The pipeline deliberately has no registry push, cloud credentials or deployment
stage. PostgreSQL runtime checks and the Compose deployment are separate from
its SQLite tests. Ansible, Terraform and monitoring tools are proposed extensions
unless accompanied by their own execution records.

For evidence, save the build number, commit SHA, result, console log, test report
and stage-view screenshot together. Do not substitute a source-file screenshot
for a successful execution record.
