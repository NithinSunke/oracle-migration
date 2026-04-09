#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r backend/requirements/dev.txt
.venv/bin/celery -A worker.celery_app:celery_app worker --loglevel=info
