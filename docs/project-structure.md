# Suggested Project Structure

## Repository Layout

```text
oracle-migration-app/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── rule_engine/
│   │   ├── workers/
│   │   ├── adapters/
│   │   │   └── oracle/
│   │   └── main.py
│   ├── requirements/
│   ├── alembic/
│   └── README.md
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── types/
│   │   └── main.tsx
│   └── README.md
├── worker/
│   ├── tasks/
│   ├── jobs/
│   ├── connectors/
│   └── README.md
├── config/
│   ├── migration-rules.example.json
│   └── environments/
├── deployment/
│   ├── docker/
│   ├── compose/
│   ├── nginx/
│   └── README.md
├── scripts/
│   ├── bootstrap/
│   ├── db/
│   └── oracle/
├── docs/
│   ├── migration-decision-engine.md
│   ├── application-architecture.md
│   └── project-structure.md
└── README.md
```

## Folder Responsibilities

### `backend/app/api`

FastAPI route handlers and API versioning.

### `backend/app/core`

Global settings, app config, logging, constants, and shared utilities.

### `backend/app/models`

Database ORM models for PostgreSQL entities.

### `backend/app/schemas`

Pydantic request and response schemas.

### `backend/app/services`

Application-level services that coordinate DB access, rule engine calls, and report generation.

### `backend/app/rule_engine`

Core recommendation engine code.

Suggested submodules:

- `loader.py`
- `normalizer.py`
- `facts.py`
- `eligibility.py`
- `scoring.py`
- `ranking.py`
- `explainer.py`

### `backend/app/workers`

Worker bootstrapping and shared job code used by Celery.

### `backend/app/adapters/oracle`

Oracle-specific integration code.

Suggested files:

- `client.py`
- `metadata.py`
- `sqlcl.py`
- `datapump.py`
- `rman.py`
- `goldengate.py`
- `zdm.py`

### `frontend/src/features`

Feature-based UI modules.

Suggested feature folders:

- `migration-intake`
- `recommendation-results`
- `history`
- `reports`
- `settings`

### `worker/tasks`

Celery task entry points.

### `worker/jobs`

Long-running workflow logic separated from task wrappers.

### `worker/connectors`

Worker-specific Oracle collection and execution helpers.

### `deployment`

Container and runtime infrastructure files.

Suggested contents:

- `compose.dev.yaml`
- `compose.prod.yaml`
- `nginx.conf`
- Dockerfiles

## Early File List

These are the first implementation files to create:

### Backend

- `backend/app/main.py`
- `backend/app/api/v1/migrations.py`
- `backend/app/api/v1/recommendations.py`
- `backend/app/schemas/migration.py`
- `backend/app/schemas/recommendation.py`
- `backend/app/services/recommendation_service.py`
- `backend/app/rule_engine/loader.py`
- `backend/app/rule_engine/scoring.py`
- `backend/app/rule_engine/explainer.py`

### Frontend

- `frontend/src/main.tsx`
- `frontend/src/app/router.tsx`
- `frontend/src/pages/NewMigrationPage.tsx`
- `frontend/src/pages/RecommendationPage.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/migration.ts`

### Worker

- `worker/tasks/recommendation_tasks.py`
- `worker/jobs/report_job.py`
- `worker/connectors/oracle_metadata_job.py`

### Deployment

- `deployment/compose/compose.dev.yaml`
- `deployment/docker/backend.Dockerfile`
- `deployment/docker/frontend.Dockerfile`
- `deployment/docker/worker.Dockerfile`
- `deployment/nginx/nginx.conf`

## Naming Conventions

- Keep API modules resource-oriented.
- Keep rule engine modules deterministic and side-effect free.
- Keep adapters thin and tool-specific.
- Keep frontend organized by feature, not by file type only.

## Extension Strategy

When you later extend this application:

- add cloud target modules under `backend/app/adapters/`
- add workflow templates under `worker/jobs/`
- add report builders under `backend/app/services/`
- add rule packs under `config/`
