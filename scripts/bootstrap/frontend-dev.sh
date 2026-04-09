#!/usr/bin/env bash
set -euo pipefail

cd frontend
npm install --no-fund --no-audit
npm run dev
