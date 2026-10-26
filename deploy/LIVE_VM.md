# Historical deployment — 16 October 2026

The owner reports the GCP trial has expired. This records an earlier deployment; it does not confirm current availability.

- Project: `project-e1a969bc-ec7e-456e-a01`
- VM: `devops`
- Zone: `asia-south1-c`
- User-selected machine: `c4-highmem-8`, Ubuntu 26.10
- Historical URL: http://34.100.207.153:80
- App directory: `~/question-generator` under the deploying SSH user
- Email/password accounts; no Google OAuth setup required
- Demo login disabled; simulated payments enabled
- PostgreSQL data persists in a Docker volume
- Docker starts on boot; containers have `restart: unless-stopped`

The user approved the screenshot's displayed estimate of $431.01/month. This is not a Free Tier VM. The screenshot also showed the trial expiring in under three days. Disk/snapshot charges may continue while a VM is stopped.

## Start and stop from PowerShell

```powershell
gcloud compute instances start devops --project=project-e1a969bc-ec7e-456e-a01 --zone=asia-south1-c
gcloud compute instances describe devops --project=project-e1a969bc-ec7e-456e-a01 --zone=asia-south1-c --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
gcloud compute instances stop devops --project=project-e1a969bc-ec7e-456e-a01 --zone=asia-south1-c
```

After starting, allow services to boot, then open `http://NEW_PUBLIC_IP:80`. The frontend uses relative `/api` URLs, so a changed IP does not require rebuilding. Update `APP_ORIGIN` in the VM's `.env` if enabling cross-origin clients; same-origin web access continues to work.

## Inspect the app

```powershell
gcloud compute ssh devops --project=project-e1a969bc-ec7e-456e-a01 --zone=asia-south1-c --tunnel-through-iap
```

Inside the VM:

```bash
cd ~/question-generator
sudo docker compose ps
sudo docker compose logs --tail=100 backend
curl -fsS http://localhost/api/health
sudo bash deploy/backup.sh
```

Do not run `docker compose down -v`: that deletes persistent database data.

## Verification

All four services started; frontend/backend/database passed their health checks. A live synthetic smoke test passed email signup/signin, PostgreSQL persistence, seven-from-ten generation, charging, both PDF export modes, real scanned-PDF Tesseract OCR, document pricing, retry-safe demo purchase, session deletion, and logout. Test documents were deleted afterward; the synthetic test account remains with a randomly generated password that was not printed.

Public access from the deployment computer was blocked by its NMIMS network policy as an unrated website. No attempt was made to bypass that block. Test from a permitted network or ask its administrator to allow the URL.

## Authentication limits

Passwords have unique random salts and scrypt hashes. Existing local sessions are preserved using a separate credentials table; the legacy internal `google_sub` column is retained only for schema compatibility, not Google authentication. There is no email verification or forgotten-password email service yet.

The requested public-IP endpoint uses HTTP, which does not encrypt passwords or session tokens in transit. Use unique demo-only passwords and non-sensitive sample documents until HTTPS is configured. The API and database are private within Docker; only the gateway publishes host ports. An existing `http-server` firewall rule was applied to this VM.
