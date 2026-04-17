# Oracle Migration App

Oracle Migration App is a web application for assessing Oracle-to-Oracle database migrations, recommending an appropriate migration approach, validating source and target readiness, and tracking execution-oriented workflows such as Data Pump jobs.

## What This App Does

The application is designed to help migration teams:

- capture migration intake details
- collect or import Oracle source metadata
- validate source-to-target compatibility
- recommend a migration approach using a rule-based decision engine
- explain why a method was selected
- store assessment history and recommendation results
- generate report outputs for review and audit
- prepare for operational workflows such as Data Pump execution

Typical migration methods considered by the platform include:

- `DATAPUMP`
- `RMAN`
- `GOLDENGATE`
- `ZDM`
- `MANUAL_REVIEW`

## Core Stack

- React + TypeScript + Vite
- FastAPI + Python
- PostgreSQL
- Celery + Redis
- NGINX
- Docker Compose
- OpenTelemetry
- Oracle adapters for metadata collection and Data Pump-style workflows

## Repository Layout

```text
oracle-migration-app/
├── backend/                  FastAPI API, services, rule engine, Oracle adapters
├── frontend/                 React application
├── worker/                   Celery worker tasks and job workflows
├── config/                   Rule configuration and environment templates
├── deployment/               Docker Compose, Dockerfiles, NGINX config
├── docs/                     Architecture, setup, and design documents
├── runtime/                  Local mount points for Oracle tools and job artifacts
├── scripts/                  Bootstrap and helper scripts
└── README.md
```

## Main Components

### Frontend

The frontend provides pages for:

- login and registration
- creating a migration assessment
- reviewing recommendations
- viewing saved history
- exporting reports
- managing Data Pump transfer jobs

### Backend

The backend exposes API endpoints for:

- migrations
- recommendations
- reports
- history
- metadata validation
- authentication
- transfer job management
- health checks

### Worker

The worker handles longer-running background activities such as:

- queued recommendation jobs
- Oracle metadata tasks
- Data Pump execution workflows

## Prerequisites

For the default Docker-based setup, install:

- Docker Engine
- Docker Compose plugin

Recommended host capacity:

- 4 CPU cores or better
- 8 GB RAM or better
- 10 GB free disk space or more

Default local ports used by the development stack:

- `3000` for frontend
- `8000` for backend API
- `8080` for NGINX reverse proxy
- `5432` for PostgreSQL
- `6379` for Redis

Optional Oracle-specific runtime requirements, only needed for live Oracle integration beyond basic app startup:

- Oracle client libraries
- Oracle Data Pump executables such as `expdp` and `impdp`
- wallet files if using wallet-based or thick-mode Oracle connectivity

## Quick Start With Docker

Run these commands from the repository root.

### 1. Clone the repository

```bash
git clone https://github.com/NithinSunke/oracle-migration.git
cd oracle-migration
```

### 2. Create the local environment file

```bash
cp config/environments/dev.env.example config/environments/dev.env
```

At minimum, review:

- PostgreSQL settings
- Redis settings
- Data Pump settings
- telemetry settings

### 3. Start the development stack

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build
```

This starts:

- `frontend`
- `backend`
- `worker`
- `postgres`
- `redis`
- `nginx`

### 4. Verify the containers are healthy

```bash
docker compose -f deployment/compose/compose.dev.yaml ps
```

Expected result:

- `backend` is `healthy`
- `postgres` is `healthy`
- `redis` is `healthy`
- `frontend`, `worker`, and `nginx` are running

### 5. Verify the backend health endpoint

```bash
curl http://localhost:8000/api/v1/health
```

Expected result:

- HTTP `200`
- JSON response showing backend status and version

### 6. Open the application

Use either of these URLs:

- `http://localhost:3000`
- `http://localhost:8080`

Useful direct endpoints:

- frontend direct: `http://localhost:3000`
- backend health: `http://localhost:8000/api/v1/health`
- reverse proxy entrypoint: `http://localhost:8080`

### 7. First validation flow inside the app

After startup, a good smoke test is:

1. register a user account
2. sign in
3. create a migration assessment
4. test source metadata collection or import Oracle metadata HTML
5. optionally validate source-to-target compatibility
6. generate a recommendation
7. open the history or reports page

## Stopping and Restarting

Stop the development stack:

```bash
docker compose -f deployment/compose/compose.dev.yaml down
```

Stop and remove volumes for a clean reset:

```bash
docker compose -f deployment/compose/compose.dev.yaml down -v
```

Restart all development services:

```bash
docker compose -f deployment/compose/compose.dev.yaml restart
```

Rebuild and restart only the frontend:

```bash
docker compose -f deployment/compose/compose.dev.yaml up -d --build frontend
```

## Runtime Files and Local Mounts

The repository includes local runtime directories used by the Docker stack:

- `runtime/oracle-tools`
  - optional mounted Oracle client or tool binaries
- `runtime/datapump-work`
  - generated Data Pump parameter files, logs, and job artifacts

If you do not need live Oracle execution tooling yet, the app can still run without a full Oracle CLI toolchain for general UI and API validation.

## Environment Files

Tracked templates:

- `config/environments/dev.env.example`
- `config/environments/prod.env.example`

Create local runtime copies as needed:

```bash
cp config/environments/dev.env.example config/environments/dev.env
cp config/environments/prod.env.example config/environments/prod.env
```

Important variables include:

- `APP_NAME`
- `APP_VERSION`
- `APP_ENV`
- `API_HOST`
- `API_PORT`
- `DATABASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `REDIS_BROKER_URL`
- `REDIS_RESULT_BACKEND`
- `TASK_ALWAYS_EAGER`
- `DATAPUMP_ENABLED`
- `DATAPUMP_EXECUTION_BACKEND`
- `DATAPUMP_EXPDP_PATH`
- `DATAPUMP_IMPDP_PATH`
- `DATAPUMP_WORK_DIR`
- `DATAPUMP_CALL_TIMEOUT_SECONDS`
- `FRONTEND_PUBLIC_API_BASE_URL`
- `OTEL_ENABLED`
- `OTEL_EXPORTER`
- `OTEL_ENVIRONMENT`
- `OTEL_SERVICE_NAMESPACE`

Do not commit real passwords, tokens, wallet files, or private connection details.

## Production-Style Startup

Create the production environment file:

```bash
cp config/environments/prod.env.example config/environments/prod.env
```

Review and replace placeholder values before startup, then run:

```bash
docker compose -f deployment/compose/compose.prod.yaml up -d --build
```

The production-style entrypoint is typically:

- `http://<host-or-ip>/`

## Where To Look Next

Use these documents for deeper detail:

- `docs/application-architecture.md`
  - system architecture and module responsibilities
- `docs/migration-decision-engine.md`
  - decision-engine intent and recommendation rules
- `docs/project-structure.md`
  - repository organization
- `docs/github-repo-setup-guide.md`
  - setup flow from a fresh GitHub checkout
- `deployment/README.md`
  - deployment-specific guidance
- `config/migration-rules.example.json`
  - example recommendation rule set

## Current Status

This repository contains implemented application code plus design and deployment documentation. It is suitable for:

- local development
- stack validation
- workflow exploration
- incremental extension of Oracle migration assessment features

Some Oracle execution capabilities depend on optional runtime tooling and environment configuration.
