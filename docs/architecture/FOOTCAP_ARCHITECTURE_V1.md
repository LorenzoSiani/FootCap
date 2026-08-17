# FootCap Architecture V1

**Status:** DRAFT — architecture decisions approved in working session; implementation may begin after repository bootstrap and Phase 0 validation.

**Document:** `docs/architecture/FOOTCAP_ARCHITECTURE_V1.md`

**Scope:** Technical architecture for FootCap V1.

---

## 1. Purpose

This document defines the technical architecture of FootCap V1.

It converts the product direction in `docs/product/FOOTCAP_MASTER_BRIEF.md` and the architecture reviews performed with Codex and Claude Code into explicit engineering decisions.

The document is intentionally opinionated. Decisions marked as **Approved** should not be reopened casually during implementation. Changes that materially affect these decisions must be documented through an Architecture Decision Record (ADR).

---

## 2. Architectural Principles

### 2.1 Data → Model → Probability → AI → User

The core FootCap flow is:

```text
DATA
  ↓
MODEL
  ↓
PROBABILITY
  ↓
AI
  ↓
USER
```

The AI layer must not become the source of official numerical predictions.

### 2.2 Modular monolith first

FootCap V1 uses a modular-monolith architecture.

We deliberately avoid independent microservices until real operational requirements justify them.

Logical boundaries are mandatory; separate deployments are not.

### 2.3 Python owns statistical intelligence

The Python Engine owns:

- ingestion;
- normalization;
- feature generation;
- model fitting;
- prediction;
- backtesting;
- evaluation.

The frontend must not reproduce statistical logic.

### 2.4 The Application API is the client contract

Web, AI tools, and future Flutter clients consume domain-oriented application APIs.

Clients must not depend directly on PostgreSQL table structure.

### 2.5 Temporal correctness is a first-class requirement

A prediction must only use information valid for its prediction cutoff.

Temporal correctness is part of the architecture, not merely a testing concern.

### 2.6 Reproducibility is mandatory

Every official model execution must be traceable to:

- dataset version;
- feature version;
- model version;
- code commit;
- dependency lock;
- training configuration;
- prediction cutoff;
- relevant artifact checksum.

### 2.7 Prefer explicit provenance over assumptions

If FootCap cannot prove when a provider made historical information available, it must not invent that timestamp.

Unknown provenance is represented as unknown.

---

## 3. System Overview

```text
                         ┌──────────────────┐
                         │   API-Football   │
                         └────────┬─────────┘
                                  │
                                  ▼
                       ┌────────────────────┐
                       │    PYTHON ENGINE   │
                       │                    │
                       │ ingestion          │
                       │ features           │
                       │ prediction         │
                       │ training           │
                       │ backtesting        │
                       └─────────┬──────────┘
                                 │
                                 ▼
                       ┌────────────────────┐
                       │   SUPABASE / PG    │
                       │                    │
                       │ domain data        │
                       │ predictions        │
                       │ provenance         │
                       │ internal data      │
                       └─────────┬──────────┘
                                 │
                                 ▼
                       ┌────────────────────┐
                       │      NEXT.JS       │
                       │                    │
                       │ UI                 │
                       │ Application API    │
                       │ AI orchestration   │
                       └─────────┬──────────┘
                                 │
                         ┌───────┴───────┐
                         ▼               ▼
                       Browser           AI
                                         │
                                         ▼
                                   FootCap Tools
```

### Core deployment model

- **Next.js / Vercel:** web application and Application API/BFF.
- **Supabase:** PostgreSQL, Auth, database security primitives.
- **Python Engine:** batch and model workloads.
- **GitHub Actions:** initial scheduler/orchestrator for Python jobs and CI.
- **GitHub:** source control, code review, CI and audit trail.

DigitalOcean, Redis, Celery, Kubernetes, Airflow and n8n are not required for V1.

---

## 4. Repository Architecture

Target V1 structure:

```text
FootCap/
├── apps/
│   └── web/
│
├── engine/
│   ├── cli/
│   ├── ingestion/
│   ├── features/
│   ├── models/
│   ├── prediction/
│   ├── backtest/
│   ├── data/
│   ├── repositories/
│   ├── validation/
│   └── tests/
│
├── packages/
│   ├── contracts/
│   └── config/
│
├── supabase/
│   └── migrations/
│
├── tests/
│
├── tools/
│   └── change-logger/
│
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── product/
│   └── research/
│
├── logs/
│
├── .github/
│   └── workflows/
│
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── package.json
└── pnpm-workspace.yaml
```

The exact package structure may evolve during implementation, but the architectural ownership boundaries must remain.

---

## 5. Temporal Data Model

### 5.1 Objective

FootCap must distinguish:

- when an event happened;
- when FootCap requested data;
- when FootCap received data;
- when FootCap persisted data;
- what information was valid at a prediction cutoff.

### 5.2 Core timestamps

#### `event_at`

When the underlying football event actually happened.

Examples:

- fixture kickoff;
- goal;
- card;
- completed match.

#### `requested_at`

When FootCap sent a request to the provider.

#### `received_at`

When FootCap received the provider response.

#### `ingested_at`

When FootCap persisted the information into its own system.

### 5.3 Provider availability

A generic historical `source_observed_at` / provider-availability timestamp must **not** be fabricated.

API-Football exposes event timestamps and documents update frequencies, but does not provide a universal historical timestamp proving when every specific record first became available to FootCap.

Therefore:

- historical provider availability may be `UNKNOWN`;
- future live collection can establish FootCap's own observation timeline;
- raw provider responses must be retained where required.

### 5.4 Knowledge cutoff

Every official prediction has a:

```text
prediction_cutoff
```

The feature engine must operate relative to this cutoff.

A source fact is eligible only when its temporal rules permit it to be known at that cutoff.

At minimum:

```text
event_at < prediction_cutoff
```

must hold for facts that describe events that have not yet occurred.

Where provider availability is verified, the stronger rule applies:

```text
source_available_at <= prediction_cutoff
```

If provider availability cannot be established retrospectively, the prediction/backtest must be classified accordingly.

### 5.5 Backtest classes

#### Event-Time Safe

Historical backtest where future events are excluded using event time, but provider availability at the historical cutoff cannot be fully proven.

#### Knowledge-Time Verified

Prediction/backtest where the data availability timeline has been captured sufficiently to demonstrate that information was available to FootCap/provider before the cutoff.

The future prospective dataset should move progressively toward Knowledge-Time Verified status.

### 5.6 Raw provider snapshots

For future data collection, FootCap should preserve raw responses containing:

```text
provider
endpoint
request_parameters
requested_at
received_at
http_status
response_hash
payload
ingestion_run_id
```

This enables reconstruction of the FootCap observation timeline.

### 5.7 Point-in-time feature generation

Feature generation must always be parameterized by a cutoff.

Conceptually:

```text
generate_features(match_id, prediction_cutoff)
```

The feature engine must not silently use "current" database state.

Derived features are generated from point-in-time-valid source facts.

### 5.8 Temporal invariant

> A prediction may only use information whose source availability is at or before the prediction cutoff. Derived features must be computed exclusively from point-in-time-valid source facts.

---

## 6. Data Architecture

FootCap separates source facts from derived features.

### Source/domain data

Examples:

- competitions;
- seasons;
- teams;
- matches;
- match events;
- match statistics.

### Derived data

Examples:

- team form;
- attack strength;
- defensive strength;
- home advantage;
- model features.

Derived data must be reproducible from source data plus an explicit feature version.

### Initial conceptual entities

```text
competitions
seasons
teams
matches
match_events
match_statistics

features / feature_snapshots

datasets
ingestion_runs
raw_provider_responses

training_runs
model_artifacts
prediction_runs
predictions

backtest_runs
backtest_folds
```

The physical schema will be finalized through Supabase migrations.

---

## 7. Model Run Contract

### 7.1 Separation of concerns

FootCap distinguishes:

```text
DATASET
   ↓
TRAINING RUN
   ↓
MODEL ARTIFACT
   ↓
PREDICTION RUN
   ↓
PREDICTION
```

A training run is not the same thing as a prediction run.

### 7.2 Dataset identity

A dataset must have a stable identity/version.

Conceptual fields:

```text
dataset_id
dataset_version
competition
seasons
source
snapshot_hash
schema_version
created_at
```

### 7.3 Training Run

A Training Run identifies one model-fitting execution.

Conceptual fields:

```text
id
model_name
model_version
dataset_version
feature_version
training_window_start
training_window_end
training_cutoff_policy
parameters
seed
code_commit
dependency_lock_hash
status
created_at
```

### 7.4 Model Artifact

A successful training run produces an identifiable artifact.

Conceptual fields:

```text
artifact_id
storage_reference
checksum
format
size
created_at
```

### 7.5 Prediction Run

A Prediction Run identifies the use of a model artifact for a specific prediction context.

Conceptual fields:

```text
id
training_run_id
match_id
prediction_cutoff
prediction_horizon
feature_version
evaluation_context
status
created_at
```

Supported contexts include:

```text
BACKTEST
PRODUCTION
EXPERIMENT
```

### 7.6 Prediction output

V1 Dixon-Coles 1X2 output:

```text
home_probability
draw_probability
away_probability
```

The values must form a valid probability distribution within defined numerical tolerance.

### 7.7 Immutability

Completed Training Runs, Model Artifacts, Prediction Runs and official Predictions are immutable.

A change creates a new run/version rather than mutating historical provenance.

### 7.8 Reproducibility invariant

> Every production or backtest prediction must be traceable to an immutable Prediction Run, which must be traceable to an immutable Training Run and its exact dataset, feature definition, code revision, dependencies and model configuration.

---

## 8. Prediction Architecture

V1 baseline model:

```text
Dixon-Coles
```

The model is the official numerical source for 1X2 probabilities.

The AI layer does not alter official probabilities.

Future models may include:

- Poisson variants;
- Elo;
- machine-learning models;
- ensembles.

These must preserve the same Model Run / Prediction Run provenance contract.

---

## 9. Backtesting Architecture

The initial evaluation approach is rolling-origin backtesting.

Conceptually:

```text
Historical data
      ↓
Training cutoff T1
      ↓
Point-in-time features
      ↓
Train
      ↓
Predict
      ↓
Evaluate

Training cutoff T2
      ↓
...
```

A Backtest Run may contain multiple folds.

Each fold should preserve:

```text
training_cutoff
prediction_cutoff
training context
prediction
actual result
metrics
```

Primary metrics for V1:

- Log Loss;
- Brier Score;
- calibration;
- sample size;
- comparison against a baseline.

The initial historical benchmark is classified as Event-Time Safe unless provider availability can be demonstrated.

---

## 10. Application API Architecture

### 10.1 Protocol

V1 uses:

```text
REST + JSON
```

with:

```text
/api/v1/
```

No GraphQL or gRPC in V1.

### 10.2 API ownership

The Application API is the client-facing domain contract.

Clients must not depend directly on database table names or schema.

### 10.3 Target endpoint set

#### Competitions

```text
GET /api/v1/competitions
GET /api/v1/competitions/:id
GET /api/v1/competitions/:id/seasons
```

#### Matches

```text
GET /api/v1/matches
GET /api/v1/matches/:id
GET /api/v1/matches/:id/events
GET /api/v1/matches/:id/statistics
```

#### Predictions

```text
GET /api/v1/matches/:id/prediction
GET /api/v1/matches/:id/predictions
```

#### Teams

```text
GET /api/v1/teams
GET /api/v1/teams/:id
GET /api/v1/teams/:id/form
GET /api/v1/teams/:id/statistics
```

#### Models

```text
GET /api/v1/models
GET /api/v1/models/:id
```

#### Backtests

```text
GET /api/v1/backtests
GET /api/v1/backtests/:id
```

### 10.4 Initial implementation subset

The first vertical slice does not need every endpoint.

Minimum target:

```text
GET /api/v1/matches
GET /api/v1/matches/:id
GET /api/v1/matches/:id/prediction
GET /api/v1/models/:id
GET /api/v1/backtests/:id
```

### 10.5 API error contract

Errors must use a consistent shape:

```json
{
  "error": {
    "code": "MATCH_NOT_FOUND",
    "message": "Match not found",
    "request_id": "req_123"
  }
}
```

### 10.6 Request IDs

Every API request should have a traceable request ID.

### 10.7 Pagination

Collection endpoints use pagination.

Offset pagination is sufficient for V1.

### 10.8 AI tool layer

AI does not receive unrestricted database access.

Instead, AI uses semantic tools such as:

```text
get_match
get_prediction
get_team_form
get_team_statistics
compare_teams
get_model_info
```

These tools resolve through controlled application/service logic.

The AI must not execute arbitrary SQL.

### 10.9 Historical prediction protection

The public application API must not expose an arbitrary historical cutoff mechanism that could imply a verified historical prediction when the required provenance is unavailable.

Historical/backtest generation remains a controlled engine operation.

---

## 11. Supabase Security Architecture

### 11.1 Role model

FootCap distinguishes:

```text
anonymous
authenticated user
Next.js server
Python Engine
admin/internal operators
```

### 11.2 API keys

New Supabase key terminology is the standard for V1:

```text
publishable key
secret key
```

The publishable key may be used in public clients.

The secret key is backend-only and must never appear in:

- browser bundles;
- Flutter clients;
- Git;
- logs;
- documentation;
- committed environment files.

### 11.3 RLS

Row Level Security is enabled on all tables exposed through the client-facing data layer.

RLS is a defense-in-depth layer and does not replace the Application API.

### 11.4 Schema separation

Conceptual separation:

```text
public
private
```

Public/domain data may be exposed through controlled policies.

Internal data remains inaccessible to browser users.

### 11.5 Public domain data

Candidate readable data:

```text
competitions
seasons
teams
matches
match_events
match_statistics
selected predictions
```

The final public exposure is determined by API/product policy.

### 11.6 Internal data

The following remain internal:

```text
raw_provider_responses
ingestion_runs
training_runs
model_artifacts
internal feature snapshots
job metadata
```

### 11.7 Browser writes

The browser must not directly create or modify authoritative football data.

Examples:

```text
matches      → no client INSERT/UPDATE/DELETE
predictions  → no client INSERT/UPDATE/DELETE
model runs   → no client write
raw data     → no client access
```

### 11.8 User data

Future user-owned tables use authenticated identity and row ownership, conceptually:

```text
user_id = auth.uid()
```

Examples:

```text
profiles
saved_matches
user_preferences
```

### 11.9 Sensitive PostgreSQL features

Views, RPC functions and `SECURITY DEFINER` functions require explicit security review.

They must not be used as shortcuts around RLS or application authorization.

---

## 12. Python Engine Architecture

### 12.1 Single engine

FootCap V1 uses one Python Engine package.

Logical modules:

```text
engine/
├── cli/
├── ingestion/
├── features/
├── models/
├── prediction/
├── backtest/
├── data/
├── repositories/
└── validation/
```

### 12.2 CLI contract

Jobs must be executable locally and by automation.

Conceptually:

```text
python -m engine ingest
python -m engine features
python -m engine train
python -m engine predict
python -m engine backtest
```

The exact CLI framework is an implementation detail.

### 12.3 Provider adapter

All API-Football interaction belongs behind a dedicated provider adapter.

The adapter owns:

- HTTP requests;
- timeouts;
- retries;
- rate limiting;
- error mapping;
- request/response logging.

Domain modules must not contain scattered raw HTTP calls.

---

## 13. Python Job Architecture

### 13.1 Job types

V1 defines:

```text
ingestion
features
training
prediction
backtest
```

### 13.2 Ingestion flow

```text
API-Football
     ↓
Provider adapter
     ↓
Raw snapshot
     ↓
Validation
     ↓
Normalization
     ↓
PostgreSQL
```

### 13.3 Ingestion Run

Each ingestion execution receives an ID and records:

```text
id
job_type
provider
started_at
finished_at
status
records_received
records_created
records_updated
errors
configuration
```

### 13.4 Idempotency

Ingestion must be idempotent wherever possible.

Provider identifiers and unique constraints are used to prevent accidental duplication.

### 13.5 Retry policy

Transient failures may be retried with exponential backoff.

Examples:

```text
429
500
502
503
504
network timeout
```

Permanent request errors should fail without pointless retries.

### 13.6 Partial failures

Ingestion supports a partial state when some records succeed and others fail.

Conceptual job states:

```text
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
CANCELLED
```

### 13.7 Concurrency

V1 deliberately limits concurrency until real workload measurements justify expansion.

PostgreSQL advisory locking or an equivalent database-backed mechanism prevents overlapping executions of mutually exclusive jobs.

Redis is not required for V1 locking.

---

## 14. Feature Job

The feature job consumes normalized source data and produces versioned feature sets.

Contract:

```text
source data
+
prediction cutoff
+
feature version
→
feature set
```

Feature generation must never silently depend on current time.

---

## 15. Training Job

Training consumes:

```text
dataset
feature version
training window
model version
parameters
```

and produces:

```text
training run
model artifact
```

Failed training runs are retained for audit and are never silently promoted to active models.

---

## 16. Prediction Job

Prediction consumes:

```text
match
model artifact
prediction cutoff
```

and produces:

```text
prediction run
prediction
```

Prediction does not mutate the model artifact.

A single model artifact may produce many prediction runs.

---

## 17. Backtest Job

Backtests are controlled engine operations.

They are not arbitrary public API operations.

Backtests should be reproducible and should preserve fold-level provenance.

---

## 18. Job Orchestration

### 18.1 V1 scheduler

GitHub Actions is the initial scheduler/orchestrator.

Its responsibility is:

```text
trigger job
provide environment
provide secrets
capture CI logs
report status
```

It must not contain FootCap domain logic.

### 18.2 Separation of scheduler and job logic

Principle:

> Schedulers trigger jobs; schedulers do not contain domain logic.

The same Python CLI must work:

- locally;
- in GitHub Actions;
- in a future dedicated worker.

### 18.3 Initial workflows

Target:

```text
.github/workflows/
├── ci.yml
├── ingestion.yml
├── training.yml
├── prediction.yml
└── backtest.yml
```

The exact schedules are implementation decisions.

### 18.4 Evolution path

```text
V1
GitHub Actions
    ↓
V2
Dedicated worker
    ↓
V3
Queue / distributed workers
```

A dedicated worker is introduced only when workload characteristics justify it.

---

## 19. Job Observability

A generic `job_run` concept may record:

```text
id
job_type
status
started_at
finished_at
trigger
git_commit
environment
error_summary
metadata
```

Domain-specific run records such as `ingestion_runs` and `training_runs` retain methodology-specific information.

GitHub Actions logs are not the authoritative application audit trail.

---

## 20. CI/CD

Every pull request should run automated checks appropriate to the code changed.

Minimum direction:

```text
Pull Request
    ↓
lint
type checks
Python checks
unit tests
migration validation
security checks
```

The exact toolchain will be selected during Phase 0.

A failed required CI check blocks merge.

---

## 21. Deployment

### Web

```text
Vercel
```

hosts the Next.js application and Application API.

### Database

```text
Supabase
```

hosts PostgreSQL and related Supabase services.

### Python

Initially executed through GitHub Actions.

### Future

Dedicated Python workers may be introduced if workload requires persistent execution, higher-frequency ingestion or parallel processing.

---

## 22. AI Architecture

### 22.1 AI is not the prediction engine

Official numerical predictions come from the statistical/modeling pipeline.

AI explains, summarizes and interacts with structured FootCap data.

### 22.2 AI Analyst

For a match, the AI may receive:

```text
match
prediction
model information
team form
relevant statistics
uncertainty/context
```

It must distinguish:

- source facts;
- model outputs;
- interpretation.

### 22.3 AI Assistant

The assistant uses controlled tools:

```text
User
 ↓
LLM
 ↓
Tool
 ↓
FootCap Application API / service layer
 ↓
Structured data
 ↓
LLM
 ↓
Answer
```

No arbitrary SQL.

No unrestricted database access.

---

## 23. Change Logger

### 23.1 Objective

FootCap should maintain an automatic project change history regardless of whether a change originated from:

- a human;
- Codex;
- Claude Code;
- ChatGPT;
- another tool.

### 23.2 Tier 1 — Git audit

Git is the authoritative source for code-change history.

Recordable metadata includes:

```text
timestamp
branch
commit
author
files changed
insertions
deletions
status
```

### 23.3 Tier 2 — agent attribution

Optional metadata may identify an originating tool:

```text
codex
claude
chatgpt
human
unknown
```

Agent attribution is best-effort and must never be represented as forensic proof.

If attribution cannot be established:

```text
source = unknown
```

### 23.4 Principle

> Better `unknown` than a false attribution.

The Change Logger must never invent authorship.

---

## 24. Testing Strategy

Testing is layered.

### Unit

- feature calculations;
- model calculations;
- temporal filters;
- API validation;
- provider parsing.

### Integration

- PostgreSQL repositories;
- Supabase migrations;
- provider adapter;
- API routes;
- job execution.

### Temporal / anti-leakage

Explicit tests must prove that:

```text
future event → excluded
future-observed source fact → excluded where availability is known
historical valid fact → included
```

### Model

- probability validity;
- deterministic execution where applicable;
- metric calculation;
- baseline comparisons.

---

## 25. Security Principles

FootCap follows defense in depth:

```text
Client
  ↓
Application API
  ↓
Application authorization
  ↓
Supabase grants
  ↓
RLS
  ↓
PostgreSQL
```

Secrets are never committed.

Backend-only credentials remain server-side.

Raw provider data and model artifacts are not client-accessible.

---

## 26. Performance Principles

V1 optimizes for correctness and simplicity before scale.

Initial strategy:

- indexed domain queries;
- pagination;
- batch ingestion;
- controlled concurrency;
- database-backed locks;
- caching only where measured to be useful.

Do not introduce distributed infrastructure before profiling demonstrates a need.

---

## 27. MVP Boundaries

The following are explicitly outside the V1 core unless requirements change:

- microservices;
- dedicated AI microservice;
- Flutter application;
- live prediction infrastructure;
- advanced ML ensembles;
- subscription/monetization;
- social features;
- personalized AI memory;
- Kubernetes;
- Redis/Celery;
- Airflow;
- n8n as core infrastructure;
- DigitalOcean worker infrastructure;
- complex event-driven architecture.

These may become future architecture layers when justified by real requirements.

---

## 28. First Vertical Slice

The first end-to-end technical milestone is:

```text
API-Football
      ↓
Historical ingestion
      ↓
Validation
      ↓
Normalization
      ↓
Supabase/PostgreSQL
      ↓
Point-in-time features
      ↓
Dixon-Coles
      ↓
Rolling backtest
      ↓
Model Run provenance
      ↓
Read-only Application API
```

The first goal is not the dashboard.

The first goal is proving that the statistical core can operate reproducibly and without temporal leakage.

---

## 29. Phase 0

Before feature development:

1. Establish monorepo tooling.
2. Configure pnpm workspace.
3. Configure Python environment.
4. Configure linting/type checks/tests.
5. Configure GitHub Actions CI.
6. Establish Supabase project/environment strategy.
7. Create initial database migration structure.
8. Establish secret management.
9. Implement Change Logger foundation.
10. Document development workflow.
11. Add initial provider adapter skeleton.
12. Add temporal/Model Run contract tests.

Phase 0 must not accidentally become feature development.

---

## 30. Architectural Decision Records

Initial ADR index:

```text
ADR-001 — Modular Monolith for V1
ADR-002 — Point-in-Time Temporal Data Model
ADR-003 — Model Run and Prediction Run Provenance
ADR-004 — REST Application API V1
ADR-005 — Supabase Security and RLS Model
ADR-006 — GitHub Actions + Python Job Architecture
ADR-007 — Change Logger Two-Tier Attribution
ADR-008 — Event-Time Safe vs Knowledge-Time Verified Backtesting
```

Each ADR should record:

```text
Context
Decision
Alternatives
Consequences
Status
```

---

## 31. Open Architectural Decisions

Only the following remain open at the architecture level:

### 31.1 Exact physical PostgreSQL schema

The conceptual entities are approved; column-level schema and indexes remain to be designed.

### 31.2 API-Football ingestion coverage

The exact endpoint set and polling schedule depend on the data required for the first vertical slice and available API plan/rate limits.

### 31.3 Feature V1 definition

The exact Dixon-Coles feature set must be specified before implementation.

### 31.4 Model artifact storage

The exact artifact storage mechanism will be chosen when the first model implementation is created.

### 31.5 Authentication scope

Supabase Auth is approved for future user accounts; the exact authentication UX is not required for the first technical vertical slice.

### 31.6 Production job schedules

Initial schedules should be conservative and may be adjusted after measuring workload and API usage.

---

## 32. Approved Architecture Summary

| Area | V1 Decision |
|---|---|
| Architecture | Modular monolith |
| Web | Next.js + TypeScript |
| API | REST + JSON |
| API version | `/api/v1` |
| Database | Supabase PostgreSQL |
| Auth | Supabase Auth when user accounts are introduced |
| Security | RLS + application authorization |
| Statistical engine | Python |
| Python architecture | One modular engine |
| Baseline model | Dixon-Coles |
| Backtesting | Rolling-origin |
| Temporal model | Point-in-time |
| Historical classification | Event-Time Safe unless availability is verified |
| Future verified dataset | Knowledge-Time Verified |
| AI | Tool-based orchestration |
| AI database access | None / no arbitrary SQL |
| Scheduler | GitHub Actions initially |
| Web deployment | Vercel |
| Python deployment | GitHub Actions initially |
| Monorepo | pnpm workspaces |
| Change logging | Git audit + best-effort agent attribution |
| Microservices | Not in V1 |
| Flutter | Future |
| n8n | Not core V1 |
| DigitalOcean | Not required V1 |
| Redis/Celery | Not required V1 |
| Kubernetes | Not required V1 |

---

## 33. Architecture Invariants

The following rules are considered non-negotiable unless an ADR explicitly changes them:

1. Official probabilities originate from the model pipeline, not from the LLM.
2. Predictions are point-in-time constrained.
3. Historical provider availability is never fabricated.
4. Completed model/prediction runs are immutable.
5. Official predictions remain traceable to their provenance chain.
6. Clients consume domain APIs rather than database tables.
7. AI does not receive arbitrary SQL/database access.
8. Browser clients cannot mutate authoritative football data.
9. Secret backend credentials are never exposed to clients.
10. Scheduler logic remains separate from Python domain logic.
11. Change attribution is never falsely asserted.
12. New infrastructure must be justified by an actual requirement or measured bottleneck.

---

## 34. Next Step

With Architecture V1 approved, implementation begins with **Phase 0**.

The first coding work should establish:

```text
repository
   ↓
pnpm
   ↓
Next.js skeleton
   ↓
Python Engine skeleton
   ↓
Supabase migrations
   ↓
CI
   ↓
Change Logger
   ↓
provider adapter
   ↓
temporal/model contract tests
```

Only after this foundation is green should the first ingestion and Dixon-Coles implementation begin.
