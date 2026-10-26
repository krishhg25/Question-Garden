#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
chmod 700 backups
umask 077
backup="backups/questiongarden-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose exec -T db pg_dump -U questiongarden -d questiongarden --clean --if-exists | gzip > "$backup"
gzip -t "$backup"
echo "Database, source files, and sessions backed up to $backup"
