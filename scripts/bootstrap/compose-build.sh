#!/usr/bin/env bash
set -euo pipefail

env BUILDX_CONFIG=/tmp/buildx docker compose -f deployment/compose/compose.dev.yaml build
