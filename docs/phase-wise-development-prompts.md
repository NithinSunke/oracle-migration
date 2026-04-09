# Phase-Wise Development Prompts

## Purpose

This guide provides ready-to-use prompts for building the Oracle migration web application in phases.

Each phase includes:

- objective
- build prompt
- test prompt
- validate prompt
- expected output

These prompts are designed for the agreed stack:

- `React`
- `TypeScript`
- `Vite`
- `FastAPI`
- `Python`
- `PostgreSQL`
- `Celery`
- `Redis`
- `NGINX`
- `Docker Compose`
- `OpenTelemetry`

## How To Use

Use one phase at a time.

Do not combine multiple phases in a single implementation prompt unless the earlier phase is already complete and verified.

For each phase:

1. run the build prompt
2. run the test prompt
3. run the validate prompt
4. only then move to the next phase

## Phase 0: Repository Bootstrap

### Objective

Create the initial backend, frontend, worker, deployment, and configuration scaffolding based on the project structure.

### Build Prompt

```text
Build Phase 0 for the Oracle Migration App.

Use the existing repository structure and create the initial project scaffolding for:
- frontend with React, TypeScript, and Vite
- backend with FastAPI
- worker with Celery
- deployment files for Docker Compose and NGINX

Requirements:
- keep code modular and aligned with docs/project-structure.md
- create minimal runnable placeholders only
- do not implement business logic yet
- add README or placeholder files only where needed

Deliverables:
- backend app entry point
- frontend app entry point
- worker bootstrap
- base Dockerfiles
- base Compose file
- base NGINX config
```

### Test Prompt

```text
Test Phase 0 for the Oracle Migration App.

Verify that:
- frontend scaffold installs and starts
- backend scaffold installs and starts
- worker process can initialize
- Docker Compose configuration is structurally valid
- no missing imports or broken entry points exist

Return:
- commands executed
- pass or fail result for each check
- exact files that need fixes if anything fails
```

### Validate Prompt

```text
Validate Phase 0 deliverables against docs/project-structure.md and docs/application-architecture.md.

Check that:
- directory structure matches the design
- backend, frontend, worker, and deployment folders exist
- starter files are consistent with the agreed stack
- no unnecessary tools were introduced

Return:
- validation summary
- design mismatches
- recommended fixes before Phase 1
```

### Expected Output

- runnable scaffold
- valid folder structure
- no business logic yet

## Phase 1: Core Backend API

### Objective

Build the FastAPI application with core request and recommendation APIs.

### Build Prompt

```text
Build Phase 1 for the Oracle Migration App.

Implement the backend API foundation in FastAPI.

Requirements:
- create app startup in backend/app/main.py
- create versioned routes under backend/app/api/v1
- create schemas for migration request and recommendation response
- add a health endpoint
- add a placeholder recommendation endpoint
- keep rule logic mocked for now
- structure code for future PostgreSQL integration

Required endpoints:
- GET /api/v1/health
- POST /api/v1/migrations
- GET /api/v1/migrations/{request_id}
- POST /api/v1/recommendations
- GET /api/v1/recommendations/{request_id}

Deliverables:
- FastAPI app
- request and response schemas
- route modules
- minimal service layer
```

### Test Prompt

```text
Test Phase 1 backend implementation.

Verify that:
- the FastAPI app starts without errors
- all required routes are registered
- request validation works for valid and invalid payloads
- health endpoint returns success
- recommendation endpoint returns structured placeholder output

Return:
- test approach
- API checks performed
- failed routes or schema mismatches
```

### Validate Prompt

```text
Validate Phase 1 against docs/migration-decision-engine.md and docs/application-architecture.md.

Check that:
- API contracts align with the documented request and response model
- route names follow the design
- schemas support future rule engine integration
- no Oracle execution logic is embedded in route handlers

Return:
- validation summary
- contract gaps
- refactoring needed before Phase 2
```

### Expected Output

- working API shell
- documented routes
- stable schema baseline

## Phase 2: Rule Engine Implementation

### Objective

Implement the rule engine that evaluates migration inputs and recommends a migration method.

### Build Prompt

```text
Build Phase 2 for the Oracle Migration App.

Implement the rule engine using the existing config/migration-rules.example.json and docs/migration-decision-engine.md.

Requirements:
- create modules for rule loading, normalization, derived facts, eligibility, scoring, ranking, and explanation
- keep the logic deterministic and side-effect free
- return recommendation, score, confidence, why, rejected approaches, and prerequisites
- support companion tool recommendation such as AutoUpgrade
- integrate the rule engine into the recommendation API

Deliverables:
- backend/app/rule_engine/*
- recommendation service integration
- explainable API response
```

### Test Prompt

```text
Test Phase 2 rule engine implementation.

Verify that:
- rules load correctly from JSON
- derived facts are computed correctly
- each migration method can be marked eligible, conditionally eligible, or not eligible
- ranking is deterministic for the same input
- response includes score, confidence, reasons, and rejected approaches

Create tests for at least these scenarios:
- small database with long downtime
- large database with low downtime
- subset migration with schema remap
- Exadata target eligible for ZDM
- upgrade scenario requiring AutoUpgrade as companion

Return:
- scenarios tested
- expected vs actual recommendation
- rule defects or scoring conflicts
```

### Validate Prompt

```text
Validate Phase 2 rule engine against docs/migration-decision-engine.md.

Check that:
- eligibility and scoring are separated
- size is a factor but not the only factor
- output is explainable
- unsupported combinations return manual review where appropriate
- the rule version is visible or trackable

Return:
- validation summary
- rule design gaps
- edge cases to address before Phase 3
```

### Expected Output

- working decision engine
- explainable recommendations
- reusable scoring modules

## Phase 3: PostgreSQL Persistence Layer

### Objective

Store migration requests, recommendations, rule versions, and audit data in PostgreSQL.

### Build Prompt

```text
Build Phase 3 for the Oracle Migration App.

Implement PostgreSQL persistence for:
- migration requests
- recommendation results
- rule evaluation audit
- rule version tracking

Requirements:
- create database models
- create persistence services
- store each recommendation with the input payload and rules version
- support fetch by request_id
- keep DB logic separate from API handlers

Deliverables:
- database models
- persistence services
- migration or schema setup files
- API integration for save and fetch
```

### Test Prompt

```text
Test Phase 3 persistence.

Verify that:
- request payloads are saved correctly
- recommendation results are saved and retrieved correctly
- audit details persist with rule version
- duplicate request handling is defined
- fetch endpoints return stored data accurately

Return:
- DB operations tested
- schema issues
- data integrity findings
```

### Validate Prompt

```text
Validate Phase 3 persistence against docs/application-architecture.md and docs/migration-decision-engine.md.

Check that:
- PostgreSQL stores application metadata only
- Oracle is not used as the control-plane database
- recommendations are auditable
- rule version traceability exists

Return:
- validation summary
- schema gaps
- risks before Phase 4
```

### Expected Output

- persisted recommendation workflow
- auditable decisions
- stable storage foundation

## Phase 4: Frontend Intake and Recommendation UI

### Objective

Build the user-facing web UI for intake forms and recommendation results.

### Build Prompt

```text
Build Phase 4 for the Oracle Migration App.

Implement the frontend with:
- migration intake form
- recommendation result page
- API integration for create and fetch
- pages aligned with docs/application-architecture.md

Requirements:
- use React, TypeScript, and Vite
- organize code by feature
- use typed API models
- show recommendation, confidence, why, prerequisites, risk flags, and rejected approaches
- keep styling clean and enterprise-ready

Deliverables:
- routing
- form page
- result page
- API service layer
- shared types
```

### Test Prompt

```text
Test Phase 4 frontend implementation.

Verify that:
- form captures required migration inputs
- invalid input is blocked or clearly surfaced
- recommendation API integration works
- result page renders the full recommendation payload
- loading and error states are handled

Return:
- screens tested
- UI defects
- API integration defects
```

### Validate Prompt

```text
Validate Phase 4 frontend against docs/application-architecture.md.

Check that:
- pages match the planned user flow
- UI exposes explainability, not only final recommendation
- frontend is not tightly coupled to internal rule implementation
- typed models match API contracts

Return:
- validation summary
- UX gaps
- contract mismatches
```

### Expected Output

- usable web interface
- intake-to-result flow
- clear recommendation display

## Phase 5: Celery Worker and Redis Integration

### Objective

Move long-running or asynchronous work into workers.

### Build Prompt

```text
Build Phase 5 for the Oracle Migration App.

Implement Celery and Redis integration for asynchronous jobs.

Requirements:
- create worker bootstrap
- configure Redis as broker/backend as needed
- move report generation or long recommendation jobs into Celery tasks
- add job status tracking hooks
- keep API responsive

Deliverables:
- worker configuration
- task modules
- async job trigger from API
- status model or placeholder status handling
```

### Test Prompt

```text
Test Phase 5 worker integration.

Verify that:
- Celery worker starts successfully
- Redis connectivity works
- API can enqueue a job
- worker processes the job
- job status can be tracked or retrieved

Return:
- tasks tested
- queue or worker failures
- retry and error handling observations
```

### Validate Prompt

```text
Validate Phase 5 against docs/application-architecture.md.

Check that:
- worker logic is separate from the API process
- asynchronous responsibilities are correctly assigned
- API performance is improved for long-running tasks
- the design supports future Oracle metadata collection

Return:
- validation summary
- architecture mismatches
- readiness for Phase 6
```

### Expected Output

- async task foundation
- scalable worker model

## Phase 6: Oracle Metadata Connector Layer

### Objective

Connect to Oracle databases to collect metadata and enrich recommendations.

### Build Prompt

```text
Build Phase 6 for the Oracle Migration App.

Implement the Oracle connector layer using python-oracledb.

Requirements:
- create Oracle client wrapper
- support secure connection configuration
- collect basic metadata required by the decision engine
- return structured metadata, not raw query dumps
- keep Oracle access in adapters or worker connectors only

Suggested metadata:
- Oracle version
- deployment type
- database size
- archivelog status
- platform
- RAC status
- TDE status
- character set

Deliverables:
- oracle client adapter
- metadata query module
- worker job to collect metadata
- integration path to feed collected data into recommendations
```

### Test Prompt

```text
Test Phase 6 Oracle metadata integration.

Verify that:
- Oracle connectivity works with configured credentials
- metadata queries return structured results
- connector errors are handled safely
- collected values map correctly into the rule engine input model

Return:
- metadata fields tested
- connection issues
- mapping issues
```

### Validate Prompt

```text
Validate Phase 6 against docs/application-architecture.md and docs/migration-decision-engine.md.

Check that:
- Oracle connectivity is isolated in adapter layers
- metadata collected matches decision engine needs
- no Oracle command execution is embedded in API handlers
- enriched recommendations improve recommendation quality

Return:
- validation summary
- connector design gaps
- readiness for Phase 7
```

### Expected Output

- Oracle-aware recommendation inputs
- reusable connector layer

## Phase 7: Reporting and Audit Views

### Objective

Generate downloadable reports and expose recommendation history.

### Build Prompt

```text
Build Phase 7 for the Oracle Migration App.

Implement reporting and audit capabilities.

Requirements:
- add history page in the frontend
- add report generation service in the backend or worker
- support downloadable JSON or PDF summary
- expose stored recommendation history
- include rule version, score, confidence, and reasons in reports

Deliverables:
- history API
- history UI
- report generation workflow
- downloadable report format
```

### Test Prompt

```text
Test Phase 7 reporting and audit features.

Verify that:
- historical requests can be listed
- a stored recommendation can be reopened
- generated reports contain all expected fields
- report downloads work

Return:
- report scenarios tested
- missing fields
- audit trail issues
```

### Validate Prompt

```text
Validate Phase 7 against the architecture and decision-engine design.

Check that:
- reports are explainable and auditable
- history data is consistent with stored recommendations
- rule version appears in the audit and report path

Return:
- validation summary
- reporting gaps
- final fixes before infrastructure hardening
```

### Expected Output

- downloadable reports
- recommendation history
- audit-ready outputs

## Phase 8: Deployment and Runtime Hardening

### Objective

Prepare the application for stable deployment with NGINX, Docker Compose, and observability.

### Build Prompt

```text
Build Phase 8 for the Oracle Migration App.

Implement deployment and runtime hardening.

Requirements:
- create Dockerfiles for frontend, backend, and worker
- create Docker Compose for app stack
- configure NGINX for frontend and API routing
- add environment-based configuration
- add OpenTelemetry instrumentation for API and workers

Deliverables:
- container build files
- compose file
- nginx config
- environment config handling
- telemetry hooks
```

### Test Prompt

```text
Test Phase 8 deployment setup.

Verify that:
- all containers build successfully
- Docker Compose starts the stack
- frontend can reach backend through NGINX
- worker can reach Redis and PostgreSQL
- telemetry initialization does not break startup

Return:
- deployment checks
- container issues
- routing or config defects
```

### Validate Prompt

```text
Validate Phase 8 deployment against docs/application-architecture.md.

Check that:
- the deployment topology matches the agreed architecture
- containers map cleanly to frontend, api, worker, redis, postgres, and nginx roles
- runtime configuration is environment-safe
- observability is present but not intrusive

Return:
- validation summary
- operational gaps
- go-live readiness assessment
```

### Expected Output

- deployable application stack
- runtime visibility
- stable operational baseline

## Final Consolidation Prompt

Use this after all phases are complete.

```text
Review the Oracle Migration App end to end.

Validate:
- architecture alignment
- API contract stability
- rule engine correctness
- persistence integrity
- frontend usability
- worker separation
- Oracle connector boundaries
- reporting completeness
- deployment readiness

Return:
- major findings
- medium-risk findings
- low-risk cleanup items
- recommended next development phase
```

