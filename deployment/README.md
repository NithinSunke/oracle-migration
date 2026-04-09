# Deployment Guide

This document describes how to configure, start, validate, and operate the Oracle Migration App in both development and production-style environments.

## Overview

The application is deployed as a multi-container stack:

- `frontend`
  - React and Vite application served by NGINX
- `backend`
  - FastAPI service exposing `/api/v1`
- `worker`
  - Celery worker for background processing
- `postgres`
  - application database
- `redis`
  - Celery broker and result backend
- `nginx`
  - reverse proxy for frontend and backend routing

## Files Used For Deployment

- [compose.dev.yaml](/docker/oracle-migration-app/deployment/compose/compose.dev.yaml)
  - local development and validation stack
- [compose.prod.yaml](/docker/oracle-migration-app/deployment/compose/compose.prod.yaml)
  - production-style stack
- [backend.Dockerfile](/docker/oracle-migration-app/deployment/docker/backend.Dockerfile)
  - backend runtime image
- [worker.Dockerfile](/docker/oracle-migration-app/deployment/docker/worker.Dockerfile)
  - worker runtime image
- [frontend.Dockerfile](/docker/oracle-migration-app/deployment/docker/frontend.Dockerfile)
  - frontend build and runtime image
- [nginx.conf](/docker/oracle-migration-app/deployment/nginx/nginx.conf)
  - reverse proxy configuration
- [frontend.conf](/docker/oracle-migration-app/deployment/nginx/frontend.conf)
  - static frontend serving configuration
- [dev.env](/docker/oracle-migration-app/config/environments/dev.env)
  - development environment values
- [prod.env](/docker/oracle-migration-app/config/environments/prod.env)
  - production environment template

## Prerequisites

Install these before starting the application:

- Docker Engine
- Docker Compose plugin
- at least 4 GB RAM available for containers
- local ports available:
  - `3000`
  - `8000`
  - `8080`
  - `5432`
  - `6379`

## Development Deployment

Run from the repository root:

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build
```

### Development URLs

- Frontend direct:
  - `http://localhost:3000`
- Reverse proxy entrypoint:
  - `http://localhost:8080`
- Backend API health:
  - `http://localhost:8000/api/v1/health`

### Stop Development Stack

```bash
docker compose -f deployment/compose/compose.dev.yaml down
```

### Stop And Remove Volumes

Use this only when you want a clean local reset:

```bash
docker compose -f deployment/compose/compose.dev.yaml down -v
```

## Production-Style Deployment

First update the production environment file:

- copy values into [prod.env](/docker/oracle-migration-app/config/environments/prod.env)
- replace placeholder passwords
- verify database and Redis settings
- verify telemetry settings if observability is required

Start the production-style stack:

```bash
docker compose -f deployment/compose/compose.prod.yaml up -d --build
```

### Production-Style URL

- Reverse proxy:
  - `http://<host-or-ip>/`

### Stop Production-Style Stack

```bash
docker compose -f deployment/compose/compose.prod.yaml down
```

## Environment Configuration

Runtime configuration is driven by environment files under [config/environments](/docker/oracle-migration-app/config/environments).

### Core Application Settings

- `APP_NAME`
  - application identifier
- `APP_VERSION`
  - release version shown by the backend
- `APP_ENV`
  - `development` or `production`
- `API_HOST`
  - backend bind host
- `API_PORT`
  - backend bind port

### Database Settings

- `DATABASE_URL`
  - SQLAlchemy connection string used by backend and worker
- `POSTGRES_DB`
  - PostgreSQL database name
- `POSTGRES_USER`
  - PostgreSQL user
- `POSTGRES_PASSWORD`
  - PostgreSQL password

### Redis And Worker Settings

- `REDIS_BROKER_URL`
  - Celery broker
- `REDIS_RESULT_BACKEND`
  - Celery result backend
- `TASK_ALWAYS_EAGER`
  - use `false` for normal containerized runtime
- `DATAPUMP_ENABLED`
  - enables actual Oracle Data Pump execution from the worker
- `DATAPUMP_EXECUTION_BACKEND`
  - `auto`, `cli`, or `db_api`
  - `auto` prefers local `expdp` and `impdp`, then falls back to `DBMS_DATAPUMP`
- `DATAPUMP_EXPDP_PATH`
  - path to the `expdp` executable inside the worker container
- `DATAPUMP_IMPDP_PATH`
  - path to the `impdp` executable inside the worker container
- `DATAPUMP_WORK_DIR`
  - writable worker directory used for generated parfiles and job artifacts
- `DATAPUMP_CALL_TIMEOUT_SECONDS`
  - maximum runtime for a single Data Pump subprocess

### Frontend And API Routing

- `FRONTEND_PUBLIC_API_BASE_URL`
  - public API base path
- `VITE_API_BASE_URL`
  - build-time frontend API base value passed through compose

### Observability

- `OTEL_ENABLED`
  - enables OpenTelemetry output
- `OTEL_EXPORTER`
  - currently configured for console exporter in templates
- `OTEL_ENVIRONMENT`
  - deployment environment label
- `OTEL_SERVICE_NAMESPACE`
  - service namespace for telemetry

## Validation Steps After Startup

### 1. Check Container Status

Development:

```bash
docker compose -f deployment/compose/compose.dev.yaml ps
```

Production-style:

```bash
docker compose -f deployment/compose/compose.prod.yaml ps
```

Expected result:

- `backend` should be `healthy`
- `postgres` should be `healthy`
- `redis` should be `healthy`
- `frontend`, `worker`, and `nginx` should be `Up`

### 2. Check Backend Health

```bash
curl http://localhost:8000/api/v1/health
```

Expected result:

- HTTP `200`

### 3. Open The Web Application

Development:

- `http://localhost:3000`
- or `http://localhost:8080`

Production-style:

- `http://<host-or-ip>/`

### 4. Validate Main Functional Areas

After login and navigation, validate:

- create a migration assessment
- test source connection
- optionally validate source-to-target migration
- generate recommendation
- open reports page

## Restart Commands

Restart all development services:

```bash
docker compose -f deployment/compose/compose.dev.yaml restart
```

Restart only frontend:

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build frontend
```

Restart only backend and worker:

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build backend worker
```

## Logs And Troubleshooting

View all development logs:

```bash
docker compose -f deployment/compose/compose.dev.yaml logs -f
```

View frontend logs:

```bash
docker compose -f deployment/compose/compose.dev.yaml logs -f frontend
```

View backend logs:

```bash
docker compose -f deployment/compose/compose.dev.yaml logs -f backend
```

View worker logs:

```bash
docker compose -f deployment/compose/compose.dev.yaml logs -f worker
```

View postgres logs:

```bash
docker compose -f deployment/compose/compose.dev.yaml logs -f postgres
```

### Common Issues

#### Frontend Shows Old UI

Use:

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build frontend
```

Then open a new browser tab or hard refresh.

#### Backend Is Unhealthy

Check:

- `DATABASE_URL`
- Postgres container health
- backend logs

#### Source Oracle Connection Test Fails

Check:

- source host
- source port
- service name
- username and password
- `SYSDBA` mode if using `sys`
- network reachability from the backend runtime

#### Target Validation Fails

Check:

- target validation is enabled in the UI
- target connection details are filled
- target is reachable from the backend runtime
- source and target versions and roles are valid

## Deployment Notes

- source metadata collection requires valid Oracle source connection details
- target validation is optional and only used for source-to-target compatibility checks
- persisted records do not store Oracle passwords
- frontend static assets are cached, but the main `index.html` is served with no-cache headers to reduce stale UI issues
- direct Data Pump execution can use either Linux-compatible `expdp` and `impdp` binaries inside the worker container, or Oracle `DBMS_DATAPUMP` through the database connection
- the compose files mount [runtime/oracle-tools](D:/LIFT-APPS/oracle-migration-app/runtime/oracle-tools) to `/opt/oracle-tools` and [runtime/datapump-work](D:/LIFT-APPS/oracle-migration-app/runtime/datapump-work) to `/var/lib/oracle-migration/datapump`

## Data Pump Runtime Preparation

To enable actual Data Pump execution in the dev stack:

1. Set `DATAPUMP_ENABLED=true` in [config/environments/dev.env](D:/LIFT-APPS/oracle-migration-app/config/environments/dev.env).
2. Choose `DATAPUMP_EXECUTION_BACKEND=auto`, `cli`, or `db_api`.
3. If you want the CLI path, place Linux-compatible `expdp` and `impdp` binaries, plus any required Oracle shared libraries, under [runtime/oracle-tools](D:/LIFT-APPS/oracle-migration-app/runtime/oracle-tools).
4. Rebuild the worker container:

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build worker backend frontend
```

5. Open the Transfers page and confirm the runtime readiness banner shows a resolved backend and no blockers.

If the page still shows blockers, verify:

- `DATAPUMP_ENABLED=true`
- `DATAPUMP_EXECUTION_BACKEND` is set to the intended mode
- if using the CLI path, `/opt/oracle-tools/expdp` exists in the worker container
- if using the CLI path, `/opt/oracle-tools/impdp` exists in the worker container
- if using the CLI path, the files are executable
- `/var/lib/oracle-migration/datapump` is writable inside the worker container
- if using the DB API path, the Oracle user can run `DBMS_DATAPUMP` and access the chosen Oracle DIRECTORY object

## Recommended Production Hardening

Before real production deployment, add or review:

- stronger secrets management
- external PostgreSQL instead of bundled container if required
- external Redis if required
- TLS termination
- backup and restore strategy for PostgreSQL
- OpenTelemetry exporter integration to your monitoring platform
- host firewall and reverse-proxy restrictions
- image version pinning and release tagging

## Suggested Handoff Message

Use this message if you want to communicate status to stakeholders:

`Everything looks good now. The application build, deployment flow, and report enhancements are in place. I have also documented the deployment and configuration steps for development and production-style environments.`
