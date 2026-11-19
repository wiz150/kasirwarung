#!/bin/sh
# Jalankan KasirWarung lewat gunicorn di port internal; nginx yang melayani HTTPS.
cd /home/dana/kasir || exit 1
mkdir -p logs
export COOKIE_SECURE=1
exec .venv/bin/gunicorn \
  --bind 127.0.0.1:8000 \
  --workers 2 --threads 2 --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  app:app
