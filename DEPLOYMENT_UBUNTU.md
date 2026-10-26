> Updated authentication: Google sign-in has been removed. Use email/password sign-up and sign-in; no OAuth client ID is needed. Passwords use salted scrypt hashes. Email verification and password recovery are not configured. Earlier Google-specific setup below is historical and should be skipped. See deploy/LIVE_VM.md for the deployed instance.

# Deploy Question Garden on an Ubuntu VM

These instructions run the frontend, API, and PostgreSQL on one Ubuntu VM with Docker Compose. For Google Cloud Platform, create the VM in Compute Engine; the application stack is otherwise the same as any Ubuntu VM. No deployment, cloud resource creation, or Google OAuth registration is performed automatically by this repository.

## 1. Prepare the VM and DNS

Use **Ubuntu 24.04 LTS**. A practical starting point for a small demonstration is 2 vCPUs, 4 GB RAM, and a 30 GB persistent disk. This is a sizing suggestion, not a load-tested guarantee; OCR benefits from more CPU/RAM. Budget more memory if enabling a local language model. Cloud hosting charges are real even though the app's checkout is simulated.

In Google Cloud Console:

1. Select your project and enable Compute Engine.
2. Create a VM with Ubuntu 24.04 LTS and your desired region/machine size.
3. Reserve a static external IP for the VM.
4. Allow inbound TCP **80 and 443** to this VM. Restrict SSH (22) to your own IP or use GCP IAP/OS Login. Do not open 5432, 8000, 5173, or 11434.
5. Point a domain's A record, such as `questions.example.com`, at the static IP. If an AAAA record exists, ensure it also points to this host or remove the incorrect record.

A domain with valid HTTPS is the recommended public Google sign-in setup. If you do not yet have a domain, you can test over an SSH tunnel with the loopback-only defaults in step 6.

Reference: [Google Cloud — Create a Linux VM](https://docs.cloud.google.com/compute/docs/create-linux-vm-instance).

## 2. Install Docker on Ubuntu

SSH into the VM. Run the official Docker apt-repository installation:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

The later commands assume your login can run Docker. Either prefix them with `sudo`, or deliberately grant your deployment user Docker access:

```bash
sudo usermod -aG docker "$USER"
```

Log out and back in for that change to take effect. The Docker group grants administrative control of the host, so use it only for trusted deployment users. Reference: [Docker's Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/).

## 3. Put only this app on the VM

Recommended: make the **contents of `question generator`** a separate Git repository, excluding `.env`, `.venv`, `node_modules`, databases, and backups using the included `.gitignore`. Clone that repository:

```bash
git clone YOUR_QUESTION_GENERATOR_REPOSITORY_URL question-generator
cd question-generator
```

Alternatively, upload this folder with your SSH/SFTP client. Do not upload virtual environments, local databases, or `node_modules`. The working directory should contain `compose.yaml`, `frontend`, and `backend`.

## 4. Configure Google sign-in

In Google Cloud Console for your project:

1. Open **Google Auth Platform** (or APIs & Services → Credentials in the older console).
2. Configure your app's branding, support email, and audience. While in testing, add the Google accounts you will use as test users.
3. Create an OAuth client of type **Web application**.
4. Under **Authorized JavaScript origins**, add your exact origin, for example `https://questions.example.com`. For local Vite development, add `http://localhost:5173` and `http://127.0.0.1:5173`.
5. Copy the OAuth **client ID** ending in `.apps.googleusercontent.com`.

This app uses the Google Identity Services JavaScript callback flow; it does not need a client secret or a server OAuth redirect route. Do not put a client secret into the frontend. The backend checks the ID token's audience and verified Google identity before creating an app session.

References: [Google Identity Services setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid), [server-side token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

## 5. Set deployment configuration

From the app root:

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 24
nano .env
```

Paste the generated random password and your values:

```dotenv
POSTGRES_PASSWORD=PASTE_GENERATED_HEXADECIMAL_PASSWORD
SITE_ADDRESS=questions.example.com
APP_ORIGIN=https://questions.example.com
PUBLIC_BIND=0.0.0.0
GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
ALLOW_DEMO_AUTH=false
DEMO_PAYMENTS_ENABLED=true
OLLAMA_URL=
OLLAMA_MODEL=qwen2.5:3b
```

Use your real domain in both settings. `SITE_ADDRESS` has no scheme; `APP_ORIGIN` includes `https://`. Keep `ALLOW_DEMO_AUTH=false`: the local demo account is intentionally shared and is unsuitable for a public deployment.

Keep the database password hexadecimal to avoid URL encoding problems. Do not commit `.env`. The PostgreSQL initialization password is applied only to a new volume; changing `.env` later does not automatically change the database user's password.

## 6. Start and verify

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=80 backend frontend gateway
curl -fsS https://questions.example.com/api/health
```

Expect `{"status":"ok"}`. Caddy obtains and renews the TLS certificate automatically when the domain resolves correctly and ports 80/443 are reachable. Frontend, backend, and database health checks are included. The initial build can take several minutes.

Open `https://questions.example.com`, sign in with Google, and try the sample. The API documentation is at `https://questions.example.com/docs` only if you explicitly proxy it; the shipped proxy exposes `/api/` routes and serves the SPA elsewhere. Local backend docs remain at port 8000 during development.

**No domain yet?** Leave `PUBLIC_BIND=127.0.0.1`, `SITE_ADDRESS=:80`, `APP_ORIGIN=http://localhost`, and temporarily set `ALLOW_DEMO_AUTH=true`. Start the stack, then run this on your own computer:

```bash
ssh -L 8080:127.0.0.1:80 YOUR_USER@YOUR_VM_IP
```

Open `http://localhost:8080` and use the local demo button. Do not expose the shared demo account publicly. Configure the real domain and Google client before switching the bind address to `0.0.0.0`.

## 7. Acceptance checklist

1. Sign in with a configured Google account. Confirm 100 free credits.
2. Create a text session with seven distinct supported statements; select FIB and request 10. Confirm 7 results and 7 credits charged.
3. Generate again in that session. Confirm 0 results, an exhaustion message, and no further charge.
4. Upload a native-text PDF or DOCX. Confirm the source is saved and each generated question costs 2 credits.
5. Upload a scanned English PDF. Check the OCR count in Source material and verify extracted text against the scan. Also try an image embedded in DOCX.
6. Use a fresh sample with at least four matching concept definitions to test MCQs, and three related assertions about one subject to test long answers.
7. Export both PDF modes. Confirm answers appear only in the questions-and-answers version.
8. Click the simulated ₹100 payment. Confirm 1,000 purchased credits are added and the app explicitly says no money was charged.
9. Sign out and sign in again. Confirm sessions, original downloads, and balances persist. Sign in as another account and confirm the first account's sessions are not visible.
10. Restart with `docker compose restart`. Confirm data still exists. Take and validate a backup.

The test suite also verifies concurrent credit spending and idempotent request retries. Its OCR-routing test mocks the OCR call; the scanned-file acceptance test above verifies the actual Tesseract executable on your VM.

## 8. Optional open-source model

The default engine is local, deterministic, and needs no GPU or model. To enable an optional Ollama wording pass, give the VM enough spare RAM for the chosen model and edit `.env`:

```dotenv
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:3b
```

Then:

```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b
docker compose --profile ai up -d backend
```

Ollama's port is not published. Model inference has a 75-second timeout and falls back to the extractive engine if unavailable. Large CPU-only batches may time out; test smaller batches first. Model changes affect wording, not answers or credit rules. Pin an image digest and model version for a reproducible assessed deployment. Reference: [Ollama structured output documentation](https://ollama.com/blog/structured-outputs).

## 9. Backups, updates, and rollback

Create a consistent database backup (including uploaded originals):

```bash
bash deploy/backup.sh
ls -lh backups/
```

Copy backups off the VM to private storage; a disk failure can otherwise destroy both the database and local backups. Retain `.env` securely and record the deployed Git commit. To restore a selected backup, stop application writes first; the following **replaces the current database contents** with the chosen snapshot:

```bash
docker compose stop backend frontend gateway
gunzip -c backups/YOUR_BACKUP.sql.gz | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U questiongarden -d questiongarden
docker compose up -d
```

Update after taking a backup:

```bash
git pull --ff-only
docker compose build
docker compose up -d
docker compose ps
```

For a code-only rollback, check out your previous release tag/commit and rebuild. Database schema changes need a migration/rollback plan; the initial app creates tables but does not include an automatic migration framework. `docker compose down` retains volumes; **do not use `down -v` unless you intend to erase the database and other persistent volumes**.

## 10. DevOps presentation and troubleshooting

For CI, copy `deploy/ci.yml.example` into `.github/workflows/ci.yml` in the app's independent repository. It runs Python tests, a frontend production build, and container builds. It deliberately does not auto-deploy without configured cloud access. Useful demonstration commands:

```bash
docker compose ps
docker compose logs -f --tail=100 backend
docker stats --no-stream
docker compose exec backend tesseract --version
docker compose exec db pg_isready -U questiongarden -d questiongarden
```

| Symptom | Check |
| --- | --- |
| Google origin/client error | Exact HTTPS origin in OAuth settings; `GOOGLE_CLIENT_ID` in `.env`; test-user audience; recreate backend after changes. |
| No Google button | Client ID absent; blocked Google script; browser privacy extension; inspect browser console. |
| HTTPS certificate failure | A/AAAA DNS, correct `SITE_ADDRESS`, inbound 80/443, and Caddy logs. |
| API 502 | `docker compose ps` and backend logs; PostgreSQL must be healthy first. |
| Database login fails after password change | Existing PostgreSQL volume still uses its original password. Rotate in PostgreSQL deliberately and update the app setting together. |
| Zero or fewer questions | Inspect source text and graph. MCQ/long prerequisites, unsupported grammar, repeated facts, or used facts can reduce the count. |
| OCR fails | Check Tesseract version, English language data, file validity, scan clarity, image/page limits, and VM memory. |
| Credit reset appears late | Reset is midnight Asia/Kolkata, applied on the next account request or page refresh. It is not based on the VM's local timezone. |
| Slow requests | OCR is CPU work. Try smaller documents; inspect memory/CPU; add a job queue before scaling concurrency. |

Keep the application and database on persistent storage. For a larger GCP deployment, the next step is Cloud SQL for PostgreSQL and private Cloud Storage for originals; the supplied configuration intentionally uses one VM for a comprehensible DevOps demonstration.
