# GitHub Repository Setup Guide

This guide explains how to take the code from the GitHub repository and configure the Oracle Migration App for development, validation, or a production-style deployment.

## 1. What This Application Contains

The repository includes:

- a React + Vite frontend
- a FastAPI backend
- a Celery worker for background jobs
- PostgreSQL for app data
- Redis for broker and task results
- NGINX for reverse proxy and frontend serving
- Oracle integration logic for metadata collection and Data Pump workflows

## 2. Recommended Installation Paths

Choose one of these paths:

- Docker-based setup
  - recommended for most users
  - fastest way to run the full stack
- Local developer setup
  - useful when you want to run frontend and backend processes directly for development
- Docker plus optional Oracle runtime tools
  - required when you want actual Oracle Data Pump CLI execution from the worker

## 3. Required Software

### Minimum Required For GitHub Checkout

Install these on the host:

- `git`
- internet access to reach GitHub and container/package repositories

### Required For Docker Deployment

Install:

- Docker Engine
- Docker Compose plugin

Recommended host capacity:

- 4 CPU cores or better
- 8 GB RAM or better
- at least 10 GB free disk space

Required open local ports for the default dev stack:

- `3000` for frontend
- `8000` for backend API
- `8080` for NGINX entrypoint
- `5432` for PostgreSQL
- `6379` for Redis

### Required For Local Developer Setup

Install:

- Python `3.12`
- `pip`
- `venv`
- Node.js `20.x` or newer
- `npm`

Recommended optional tools:

- `curl`
- `jq`
- a SQL client for PostgreSQL

### Optional Oracle-Specific Software

Install or provide these only if you need live Oracle integration beyond basic app startup:

- Oracle Instant Client or equivalent Oracle client libraries
- Oracle Data Pump executables such as `expdp` and `impdp`
- Oracle wallet files when using Oracle Thick mode or wallet-based target connections

In this repository, the Docker stack expects optional Oracle tools to be mounted from:

- `runtime/oracle-tools`

The app also writes generated Data Pump job artifacts to:

- `runtime/datapump-work`

## 4. Clone The Repository From GitHub

```bash
git clone https://github.com/NithinSunke/oracle-migration.git
cd oracle-migration
```

## 5. Repository Areas You Should Know

- `backend`
  - FastAPI application and Oracle service logic
- `frontend`
  - React frontend
- `worker`
  - Celery worker entrypoints and jobs
- `deployment`
  - Docker Compose files, Dockerfiles, and NGINX config
- `config/environments`
  - runtime environment templates
- `runtime`
  - local mount paths for Oracle tools and Data Pump working files
- `docs`
  - architecture, deployment, and project documentation

## 6. Environment Files

The main environment templates are:

- `config/environments/dev.env`
- `config/environments/prod.env`

### Important Variables

Core app settings:

- `APP_NAME`
- `APP_VERSION`
- `APP_ENV`
- `API_HOST`
- `API_PORT`

Database settings:

- `DATABASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Redis and worker settings:

- `REDIS_BROKER_URL`
- `REDIS_RESULT_BACKEND`
- `TASK_ALWAYS_EAGER`

Oracle Data Pump settings:

- `DATAPUMP_ENABLED`
- `DATAPUMP_EXECUTION_BACKEND`
- `DATAPUMP_EXPDP_PATH`
- `DATAPUMP_IMPDP_PATH`
- `DATAPUMP_WORK_DIR`
- `DATAPUMP_CALL_TIMEOUT_SECONDS`

Frontend routing:

- `FRONTEND_PUBLIC_API_BASE_URL`

Observability:

- `OTEL_ENABLED`
- `OTEL_EXPORTER`
- `OTEL_ENVIRONMENT`
- `OTEL_SERVICE_NAMESPACE`

### Configuration Notes

- `dev.env` is for local development and currently contains local-friendly defaults.
- `prod.env` is a template and must be edited before real deployment.
- For public or shared environments, replace all placeholder passwords.
- Do not commit real passwords, database connection strings, tokens, or wallet files back into GitHub.

## 7. Docker-Based Setup

This is the easiest way to run the app from the GitHub repository.

### Step 1. Review The Development Environment File

Check:

- `config/environments/dev.env`

At minimum, verify:

- PostgreSQL values
- Redis values
- Data Pump settings
- telemetry settings if needed

### Step 2. Start The Development Stack

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build
```

### Step 3. Validate Running Services

```bash
docker compose -f deployment/compose/compose.dev.yaml ps
curl http://localhost:8000/api/v1/health
```

Expected result:

- backend should become `healthy`
- postgres should become `healthy`
- redis should become `healthy`
- API health should return HTTP `200`

### Step 4. Open The Application

Use either:

- `http://localhost:3000`
- `http://localhost:8080`

### Step 5. Stop The Stack

```bash
docker compose -f deployment/compose/compose.dev.yaml down
```

To reset local PostgreSQL data:

```bash
docker compose -f deployment/compose/compose.dev.yaml down -v
```

## 8. Production-Style Docker Setup

### Step 1. Prepare Production Variables

Edit:

- `config/environments/prod.env`

You should change:

- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- any telemetry values you want to use
- Data Pump values if actual execution is needed

### Step 2. Start The Production-Style Stack

```bash
docker compose -f deployment/compose/compose.prod.yaml up -d --build
```

### Step 3. Validate

```bash
docker compose -f deployment/compose/compose.prod.yaml ps
```

Open:

- `http://<host-or-ip>/`

## 9. Local Developer Setup Without Docker

Use this path when you want to run frontend and Python services directly.

### Step 1. Create Python Virtual Environment And Install Dependencies

From the repository root:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements/dev.txt
```

Or use the helper script:

```bash
./scripts/bootstrap/setup-dev.sh
```

### Step 2. Install Frontend Dependencies

```bash
cd frontend
npm install --no-fund --no-audit
cd ..
```

### Step 3. Provide PostgreSQL And Redis

You still need PostgreSQL and Redis available.

You can:

- run them through Docker only
- install them locally
- point the app to managed services

### Step 4. Export Environment Variables

You can load values from `config/environments/dev.env` or export them manually.

At minimum, backend and worker need:

- `DATABASE_URL`
- `REDIS_BROKER_URL`
- `REDIS_RESULT_BACKEND`

### Step 5. Start Backend

Example:

```bash
. .venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 6. Start Worker

Example:

```bash
. .venv/bin/activate
celery -A worker.celery_app.celery_app worker --loglevel=info
```

### Step 7. Start Frontend

```bash
cd frontend
npm run dev
```

Frontend URL:

- `http://localhost:3000`

Backend URL:

- `http://localhost:8000/api/v1`

## 10. Oracle Integration Requirements

The app can run without a live Oracle endpoint for UI and general app validation, but Oracle-specific features need extra setup.

### Features That Need Oracle Connectivity

- source metadata collection
- source-to-target validation
- Oracle Thick mode validation
- wallet-based Oracle connections
- live Data Pump export and import

### For Basic Oracle Connectivity

You need:

- reachable Oracle listener host and port
- valid service name
- valid Oracle username and password

### For Thick Mode Or Wallet-Based Connectivity

You may need:

- Oracle client libraries readable by backend and worker
- wallet directory mounted into the container or available on the host
- matching `wallet_location` in the app connection settings

### For Live Data Pump CLI Execution

You need:

- `DATAPUMP_ENABLED=true`
- `expdp` and `impdp` available at the configured paths
- writable `DATAPUMP_WORK_DIR`
- Oracle connectivity from the worker container or host

The current Docker setup expects:

- `DATAPUMP_EXPDP_PATH=/opt/oracle-tools/expdp`
- `DATAPUMP_IMPDP_PATH=/opt/oracle-tools/impdp`

## 11. Post-Setup Validation Checklist

After the app starts, validate these:

- login page loads
- migration intake page opens
- backend health endpoint works
- history page opens
- recommendation flow works for saved assessments
- reports page renders
- transfer jobs page loads

If Oracle connectivity is configured, also validate:

- source connection test
- target connection test
- source-to-target validation
- dry-run Data Pump plan generation

## 12. Common Problems

### Backend Not Healthy

Check:

```bash
docker logs compose-backend-1
```

Possible causes:

- invalid environment variables
- PostgreSQL not reachable
- Redis not reachable
- Oracle Thick mode initialization failure

### Worker Cannot Run Data Pump

Check:

- `DATAPUMP_ENABLED`
- `DATAPUMP_EXECUTION_BACKEND`
- `DATAPUMP_EXPDP_PATH`
- `DATAPUMP_IMPDP_PATH`
- permissions on `runtime/datapump-work`
- presence of Oracle tools in `runtime/oracle-tools`

### Frontend Loads But API Calls Fail

Check:

- backend container health
- `VITE_API_BASE_URL`
- reverse proxy configuration
- browser network errors

### Oracle Connection Validation Fails

Check:

- host, port, service name
- network reachability from the backend or worker container
- Thick mode library path
- wallet path
- target-side ACL, wallet, or certificate requirements for Object Storage or HTTPS operations

## 13. Recommended Software Summary

For most users, install only:

- `git`
- Docker Engine
- Docker Compose plugin

For active development, also install:

- Python `3.12`
- Node.js `20+`
- `npm`

For Oracle live execution features, also provide:

- Oracle client libraries
- `expdp`
- `impdp`
- Oracle wallets when required

## 14. Suggested First Commands After Clone

### Fastest Start

```bash
git clone https://github.com/NithinSunke/oracle-migration.git
cd oracle-migration
docker compose -f deployment/compose/compose.dev.yaml up -d --build
curl http://localhost:8000/api/v1/health
```

### Local Dev Bootstrap

```bash
git clone https://github.com/NithinSunke/oracle-migration.git
cd oracle-migration
./scripts/bootstrap/setup-dev.sh
```

