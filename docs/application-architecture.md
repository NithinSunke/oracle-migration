# Oracle Migration Web Application Architecture

## Purpose

This application is a web-based decision and execution support platform for Oracle on-premises to Oracle on-premises migrations.

It helps teams:

- collect migration inputs
- recommend the right migration method
- explain why the method was chosen
- store assessment and recommendation history
- prepare for future workflow execution and reporting

## Agreed Technology Stack

### Frontend

- `React`
- `TypeScript`
- `Vite`

### Backend

- `FastAPI`
- `Python`
- `Celery`
- `Redis`

### Data Layer

- `PostgreSQL` for application metadata and audit data
- `python-oracledb` for Oracle connectivity

### Infrastructure

- `NGINX`
- `Docker Compose`
- `OpenTelemetry`

### Oracle Execution Tooling

- `SQLcl`
- `Data Pump`
- `RMAN`
- `GoldenGate`
- `ZDM`

## High-Level Architecture

```text
+---------------------------+
| React Frontend            |
| - Intake Forms            |
| - Recommendation UI       |
| - Audit and Reports       |
+-------------+-------------+
              |
              v
+---------------------------+
| NGINX Reverse Proxy       |
| - Routing                 |
| - TLS termination         |
| - Static asset serving    |
+-------------+-------------+
              |
      +-------+-------+
      |               |
      v               v
+-------------+   +------------------+
| FastAPI API |   | FastAPI Admin API |
| - Intake    |   | - Rules           |
| - Results   |   | - Config          |
| - Reports   |   | - System control  |
+------+------+   +---------+--------+
       |                      |
       +----------+-----------+
                  |
                  v
      +-----------------------------+
      | Rule Engine Service Layer   |
      | - validation                |
      | - eligibility               |
      | - scoring                   |
      | - explainability            |
      +--------------+--------------+
                     |
         +-----------+-----------+
         |                       |
         v                       v
+------------------+   +------------------+
| PostgreSQL       |   | Celery Workers   |
| - requests       |   | - assessments    |
| - recommendations|   | - report jobs    |
| - audits         |   | - connector jobs |
| - rules version  |   | - future runs    |
+------------------+   +---------+--------+
                                 |
                                 v
                      +----------------------+
                      | Redis                |
                      | - task queue         |
                      | - cache/session data |
                      +----------+-----------+
                                 |
                                 v
                     +------------------------+
                     | Oracle Tool Adapters   |
                     | - SQLcl                |
                     | - RMAN                 |
                     | - Data Pump            |
                     | - GoldenGate           |
                     | - ZDM                  |
                     +-----------+------------+
                                 |
                                 v
                     +------------------------+
                     | Source/Target Oracle   |
                     | Databases              |
                     +------------------------+
```

## Application Modules

### 1. Frontend Application

The frontend should provide:

- migration intake forms
- recommendation results
- detailed explanation of scoring
- prerequisites and risks
- saved assessments
- export/report screens

Recommended pages:

- `/`
- `/migration/new`
- `/migration/:id`
- `/recommendation/:id`
- `/history`
- `/reports`
- `/settings/rules`

## 2. API Layer

The FastAPI backend should expose:

- intake APIs
- recommendation APIs
- report APIs
- health APIs
- rules management APIs

Suggested endpoints:

- `POST /api/v1/migrations`
- `GET /api/v1/migrations/{request_id}`
- `POST /api/v1/recommendations`
- `GET /api/v1/recommendations/{request_id}`
- `GET /api/v1/rules`
- `POST /api/v1/reports/{request_id}`
- `GET /api/v1/health`

## 3. Rule Engine

This is the core business layer.

Responsibilities:

- validate incoming request payloads
- derive decision facts
- evaluate method eligibility
- compute weighted scores
- return explainable results
- attach companion tools like `AutoUpgrade`

Core internal components:

- `normalizer`
- `validator`
- `fact-deriver`
- `eligibility-engine`
- `scoring-engine`
- `recommendation-ranker`
- `explanation-builder`

## 4. Worker Layer

Workers should be separate from the API process.

Responsibilities:

- asynchronous recommendation jobs for large requests
- Oracle environment prechecks
- report generation
- metadata collection from Oracle
- future execution workflow orchestration

This separation keeps the API fast and allows scaling later.

## 5. Metadata Database

PostgreSQL stores application data only.

Suggested entities:

- migration requests
- recommendation results
- rule versions
- rule evaluation audit
- report metadata
- application settings

Oracle is not the application metadata store. Oracle remains the source and target system under assessment.

## 6. Oracle Connector and Tool Adapter Layer

This layer should wrap Oracle-native access and commands so they are not scattered across the codebase.

Recommended adapters:

- `oracle_metadata_adapter`
- `oracle_connectivity_adapter`
- `sqlcl_adapter`
- `datapump_adapter`
- `rman_adapter`
- `goldengate_adapter`
- `zdm_adapter`

Each adapter should return structured results, not raw command output only.

## 7. Observability

Use OpenTelemetry for:

- API request tracing
- worker job tracing
- rule engine timing
- connector timing
- failure diagnostics

At minimum, instrument:

- request ID
- recommendation ID
- task ID
- Oracle target identifier
- rule version

## 8. Deployment Topology

### Minimum deployment

- 1 `nginx` container
- 1 `frontend` container
- 1 `api` container
- 1 `worker` container
- 1 `redis` container
- 1 `postgres` container

### Later scale-out

- multiple API replicas
- multiple worker replicas
- dedicated report worker pool
- dedicated Oracle connector worker pool

## Data Flow

### Recommendation flow

1. User enters migration inputs in the UI.
2. Frontend sends request to FastAPI.
3. API validates payload.
4. Rule engine derives technical facts.
5. Rule engine checks eligibility and scores methods.
6. Recommendation is stored in PostgreSQL.
7. Result is returned to frontend.
8. User reviews recommendation, risks, and prerequisites.

### Future assessment flow

1. User provides Oracle connection metadata.
2. Worker gathers source metadata.
3. Worker stores collected metrics and checks.
4. Rule engine reruns recommendation with enriched data.
5. Application generates downloadable report.

## Non-Functional Requirements

- explainable recommendation output
- auditable decisions
- versioned rule definitions
- retry-safe worker jobs
- no Oracle command execution directly from the UI
- secure handling of Oracle credentials
- easy extension to cloud targets later

## Recommended Build Sequence

### Phase 1

- frontend intake form
- backend request API
- rule engine
- PostgreSQL persistence
- recommendation result page

### Phase 2

- Celery workers
- Redis queueing
- report generation
- Oracle metadata connectors

### Phase 3

- Oracle tool adapters
- execution workflow support
- rule management UI
- operational dashboards

## Design Notes

- Keep recommendation logic pure and testable.
- Keep Oracle command execution isolated in worker adapters.
- Store every recommendation with the exact rule version used.
- Do not couple UI forms directly to rule internals; use stable API contracts.
