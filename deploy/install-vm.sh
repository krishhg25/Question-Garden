#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/question-generator"
tar -xzf "$HOME/question-garden-deploy.tar.gz" -C "$HOME/question-generator"
cd "$HOME/question-generator"
if [ ! -f .env ]; then
  umask 077
  printf 'POSTGRES_PASSWORD=%s\nSITE_ADDRESS=:80\nAPP_ORIGIN=http://34.100.207.153\nPUBLIC_BIND=0.0.0.0\nALLOW_DEMO_AUTH=false\nDEMO_PAYMENTS_ENABLED=true\nOLLAMA_URL=\n' "$(openssl rand -hex 24)" > .env
fi
sudo docker compose up -d --build
sudo docker compose ps
