# FootCap Architecture V1.1

**Status:** Approved clarification before Phase 0.  
**Supersedes:** V1 as implementation baseline; V1 remains the historical record.

## 1. Purpose

V1.1 preserves the approved modular monolith, Next.js, one Python Engine, Supabase/PostgreSQL, REST + JSON, GitHub Actions, Dixon-Coles baseline, and tool-based AI layer. It resolves implementation ambiguities without adding infrastructure or microservices.

## 2. Architectural Principles

### 2.1 Data → Model → Probability → AI → User

Official numerical probabilities originate only in the statistical pipeline. AI interprets structured FootCap data and cannot invent or alter official probabilities.

### 2.2 Modular monolith first

Logical boundaries are mandatory; separate deployments are not.

### 2.3 Python owns statistical intelligence

The Python Engine owns ingestion, normalization, features, model fitting, prediction, backtesting, and evaluation. Frontend and AI do not reproduce statistical logic.

### 2.4 Application API is the client contract

Web, AI Tool Layer, and future Flutter consume domain-oriented Application API/service contracts, never PostgreSQL tables.

### 2.5 Temporal correctness and reproducibility

Every prediction has an explicit cutoff and temporal classification. Every official execution is traceable to dataset, feature snapshot, model version, code commit, dependency lock, configuration, cutoff, and artifact checksum.

## 3. System Overview

```text
API-Football → Python Engine → Supabase/PostgreSQL → Next.js → Browser
                                            ↑              ↓
                                            └── AI Tool Layer / AI
```

- **Next.js / Vercel:** web, Application API/BFF, Application Service Layer, and AI Tool Layer.
- **Supabase:** PostgreSQL, Auth, grants, RLS.
- **Python Engine:** one modular package for batch/model workloads.
- **GitHub Actions:** initial CI and scheduler/orchestrator for Python jobs.
- **GitHub:** source control, review, CI, authoritative audit of committed changes.

DigitalOcean, Redis, Celery, Kubernetes, Airflow, and n8n are not required for V1.

## 4. Repository Architecture

```text
apps/web/
engine/{cli,ingestion,features,models,prediction,backtest,data,repositories,validation,tests}/
packages/{contracts,config}/
supabase/migrations/
tests/  tools/change-logger/  docs/  logs/  .github/workflows/
```

Exact package layout may evolve, but ownership boundaries remain.

## 5. Temporal Data Model

### 5.1 Canonical fields

- **`event_at`**: underlying football event time.
- **`requested_at`**: FootCap request time.
- **`received_at`**: FootCap provider-response time.
- **`ingested_at`**: FootCap persistence time.
- **`source_available_at`**: earliest availability time FootCap can support with evidence for a source fact.

`source_observed_at` is not a V1 temporal term and must not be used as an alternative to `source_available_at`.

### 5.2 V1 timestamp convention

- Persist timestamps as timezone-aware UTC instants.
- V1 precision is milliseconds. Finer input is normalized without changing instant; coarser known precision is retained in provenance metadata.
- A prior event is eligible only when `event_at < prediction_cutoff`.
- Verified availability is eligible only when `source_available_at <= prediction_cutoff`.
- `source_available_at` is nullable only for **UNKNOWN**. UNKNOWN is never an earlier instant and cannot satisfy a Knowledge-Time Verified comparison.
- FootCap-collected raw snapshots require `requested_at`, `received_at`, and `ingested_at`. Missing `event_at` is explicit and cannot satisfy an event-time rule requiring it.

### 5.3 Source availability policy

Historical API-Football availability may be UNKNOWN and is never fabricated. For prospective collection, raw snapshots establish FootCap observation evidence. For a live-collected fact, `source_available_at = received_at` unless documented evidence supports another instant; evidence and rationale are retained.

### 5.4 Backtest classes

**Event-Time Safe** uses `event_at < prediction_cutoff` to exclude future events. Historical `source_available_at` may be UNKNOWN. It carries the Event-Time Safe classification in runs, folds, API, and AI provenance and must never be represented as Knowledge-Time Verified.

**Knowledge-Time Verified** requires `event_at < prediction_cutoff` where relevant and `source_available_at <= prediction_cutoff` for every material source fact. It is required for prospective data when availability is captured and verifiable.

### 5.5 Temporal invariant

Every run declares `temporal_classification`. Event-Time Safe requires event-time safety. Knowledge-Time Verified requires the stronger applicable event-time and availability rules. A result cannot be upgraded without supporting availability evidence.

### 5.6 Raw snapshots and point-in-time features

Retained raw snapshots include provider, endpoint, parameters, request/receive timestamps, status, response hash, payload, ingestion run ID, and availability evidence where present. Feature generation is parameterized by cutoff and classification; it cannot silently use current database state.

## 6. Data Architecture

Source/domain facts are competitions, seasons, teams, matches, match events, and statistics. Derived data includes form, strengths, home advantage, and features.

```text
competitions, seasons, teams, matches, match_events, match_statistics
datasets, feature_runs, feature_snapshots
ingestion_runs, raw_provider_responses
training_runs, model_artifacts, prediction_runs, predictions
backtest_runs, backtest_folds
```

A normalized current view may be updated idempotently, but data used by a completed dataset/snapshot remains reconstructible and immutable. The exact source-fact correction/version policy is an open decision before substantive ingestion.

## 7. Model Run Contract

### 7.1 Provenance chain

```text
Dataset → Feature Snapshot → Training Run → Model Artifact → Prediction Run → Prediction
```

Completed records do not mutate provenance; corrections and reruns create versioned records.

### 7.2 Dataset identity

`dataset_id`, `dataset_version`, competition, seasons, source, `snapshot_hash`, `schema_version`, `temporal_classification`, and `created_at` deterministically identify the source-data selection.

### 7.3 Feature Run and Feature Snapshot

`feature_version` identifies feature **logic**, not a concrete result. Every feature execution creates a `feature_run`, linked to common Job Run provenance, with input selection, cutoff(s), feature version, classification, status, and metadata.

Each immutable concrete result has `feature_snapshot_id`, `feature_snapshot_hash`, dataset ID/version, feature version, prediction cutoff, classification, `feature_run_id`, and creation time. Training and prediction reference a concrete snapshot, never only `feature_version`.

Feature generation may be internal to training/prediction. A separate `features.yml` is not required, but Feature Run and Feature Snapshot are mandatory whenever features are generated.

### 7.4 Training Run

A Training Run records `id`, model name/version, dataset ID/version, `feature_snapshot_id`, `feature_snapshot_hash`, `feature_version`, training window, cutoff policy, classification, parameters, seed, code commit, dependency-lock hash, status, and creation time. The lockfile/runtime is recoverable from recorded commit/provenance. Seed is explicit and null only when randomness does not apply.

### 7.5 Model Artifact

A successful Training Run produces immutable `artifact_id`, `training_run_id`, storage reference, checksum, format, size, and creation time.

### 7.6 Prediction Run

```text
id, training_run_id, artifact_id, match_id, prediction_cutoff,
prediction_horizon, feature_snapshot_id, feature_snapshot_hash,
feature_version, evaluation_context, temporal_classification, status, created_at
```

The artifact belongs to the stated Training Run; snapshot ID/hash match the snapshot used for match/cutoff.

- **PRODUCTION:** candidate or published user-facing output.
- **BACKTEST:** controlled historical evaluation; never official current prediction.
- **EXPERIMENT:** research/validation; never official.

### 7.7 Output, publication, reproducibility

V1 output is home/draw/away probability forming a valid distribution. Publication state is `DRAFT | PUBLISHED | SUPERSEDED | WITHDRAWN`.

Only `PUBLISHED` `PRODUCTION` predictions are official. A deterministic uniqueness rule permits no more than one published official PRODUCTION prediction for a match and prediction horizon. A replacement atomically supersedes the prior official result before publishing.

Completed feature/training/prediction/backtest records, snapshots, artifacts, and official predictions are immutable. Every production/backtest prediction traces to exact dataset, snapshot/hash, run, artifact, code, dependencies, configuration, and classification.

## 8. Prediction Architecture

Dixon-Coles is the V1 official 1X2 probability source. Future models preserve this contract. AI cannot alter official probabilities.

## 9. Backtesting Architecture

V1 uses rolling-origin backtesting:

```text
Backtest Run → Backtest Fold → one Training Run → one or more BACKTEST Prediction Runs
```

Each fold records training cutoff, prediction cutoff(s), classification, training context, linked Training Run, linked Prediction Runs, actual outcomes, metrics, and baseline comparison. A fold may predict multiple fixtures, but each remains traceable. Historical benchmarks are Event-Time Safe unless availability is demonstrated.

## 10. Application API Architecture

### 10.1 Protocol and target endpoints

V1 uses REST + JSON under `/api/v1/`; no GraphQL or gRPC. Target reads cover competitions, matches, match events/statistics, predictions, teams, models, and backtests. The first vertical slice needs match list/detail, singular prediction, model detail, and backtest detail.

### 10.2 Official and public predictions

`GET /api/v1/matches/:id/prediction` returns only the deterministic official prediction: `evaluation_context = PRODUCTION`, state `PUBLISHED`, and current non-superseded result under §7.7. It never returns BACKTEST or EXPERIMENT.

`GET /api/v1/matches/:id/predictions` is not unrestricted provenance access. Public V1 exposes only product-policy-approved PRODUCTION predictions. BACKTEST and EXPERIMENT are internal and never publicly readable through it.

The public API provides no arbitrary historical cutoff generation and never presents Event-Time Safe output as an official PRODUCTION prediction. Exposed methodology/performance information retains classification.

### 10.3 Errors, request IDs, pagination

Errors use `{"error":{"code":"MATCH_NOT_FOUND","message":"Match not found","request_id":"req_123"}}`. Every request has an ID. Collections use offset pagination with mandatory stable ordering; allowed filters/sorts are defined per endpoint before implementation.

### 10.4 AI Tool Layer

```text
AI → AI Tool Layer → Application Service Layer → data access → Supabase
```

Semantic tools include `get_match`, `get_prediction`, `get_team_form`, `get_team_statistics`, `compare_teams`, and `get_model_info`. They are not arbitrary SQL or direct database clients.

Tool outputs enforce the same publication, temporal, and provenance protection as public API. AI cannot obtain or present BACKTEST/EXPERIMENT as PRODUCTION. Outputs include relevant IDs, timestamps/freshness, classification, and provenance limits to support fact/model/interpretation/uncertainty separation.

## 11. Supabase Security Architecture

### 11.1 Principles

RLS applies to every client-exposed relation and complements Application API authorization. Raw data, artifacts, feature snapshots, and job metadata are never browser-accessible.

Next.js and Python are trusted backend components with different responsibilities, not automatically distinct PostgreSQL identities. V1 does not require DB-level identity separation. If they share a Supabase secret key, it does not create two DB principals; separation is by responsibility, secret handling, repository boundaries, grants, and review.

### 11.2 Actor matrix

| Actor | Credential | Schema | Read | Write | Restrictions |
|---|---|---|---|---|---|
| anonymous browser | publishable key / no session | exposed public domain only, if directly exposed | policy-approved public reads | none | no authoritative writes; API remains contract |
| authenticated user | publishable key + Auth session | public domain and own user tables | public reads and own rows | own user rows only | `auth.uid()`; no football/model/raw writes |
| Next.js server | backend-only secret key | public/private needed by Application Service Layer | domain and required provenance | server-authorized operations | never client-delivered; enforces API/tool policy |
| Python Engine | backend-only secret key | public/private needed for jobs | source/provenance/model inputs | ingestion/features/runs/artifacts/predictions via repositories | owns statistical writes, not client authorization |
| admin/internal operator | controlled operator credential | operational scope | operational reads | explicitly authorized writes | deliberate/logged; never browser-delivered |

Before migrations, direct browser-readable relations and RLS policies are explicitly decided. Browser access never substitutes for Application API. Browser users cannot write authoritative football data, predictions, model runs, or raw data. Views, RPC, and `SECURITY DEFINER` require security review.

## 12. Python Engine Architecture

One Python package contains CLI, ingestion, features, models, prediction, backtest, data, repositories, and validation. The same CLI runs locally and in automation: `python -m engine ingest|features|train|predict|backtest`. Provider calls remain behind one adapter owning HTTP, timeouts, retries, rate limits, error mapping, and request/response logging.

## 13. Python Job Architecture

### 13.1 Common Job Run provenance

V1 job types are ingestion, features, training, prediction, and backtest. Every execution records:

```text
job_type, status, started_at, finished_at, trigger, git_commit, git_ref,
environment, workflow_run_id, error_summary, metadata
```

The common Job Run links to `ingestion_run`, `feature_run`, `training_run`, `prediction_run`, or `backtest_run`. Specific records add methodology fields but never omit common execution provenance.

### 13.2 Ingestion, dependencies, concurrency

Ingestion follows `API-Football → adapter → raw snapshot → validation → normalization → PostgreSQL`, is idempotent where possible via provider IDs/constraints, and uses states `PENDING`, `RUNNING`, `COMPLETED`, `PARTIAL`, `FAILED`, `CANCELLED`.

Mandatory downstream rule:

```text
COMPLETED → downstream allowed
PARTIAL   → allowed only when explicit job/data policy declares the input sufficient
FAILED    → downstream blocked
CANCELLED → downstream blocked
```

Downstream runs record accepted upstream IDs and policy used for PARTIAL. They cannot infer readiness from current tables. PostgreSQL advisory locks or equivalent database-backed locks prevent overlap of mutually exclusive jobs.

## 14. Feature Job

Feature generation consumes temporally eligible normalized data, cutoff, logic version, and classification. It creates Feature Run and immutable Feature Snapshot, never silently depending on current time.

## 15. Training Job

Training consumes dataset, concrete Feature Snapshot, model version, training window, parameters; it creates Training Run and Model Artifact. Failed runs remain auditable and cannot be promoted.

## 16. Prediction Job

Prediction consumes match, artifact, concrete Feature Snapshot, cutoff, and context; it creates traceable Prediction Run and Prediction without mutating artifact.

## 17. Backtest Job

Backtests are controlled engine operations, never arbitrary public API operations, and preserve §9 provenance.

## 18. Job Orchestration

GitHub Actions triggers the CLI, provides approved environment/secrets, captures logs, and reports status; it contains no FootCap domain logic. Expected workflows are `ci.yml`, `ingestion.yml`, `training.yml`, `prediction.yml`, `backtest.yml`. `features.yml` is optional because feature generation may be internal; Feature Run provenance remains mandatory. The CLI is portable to a future worker only if justified.

## 19. Job Observability

Common Job Run provenance is the authoritative application execution record. GitHub Actions logs aid diagnosis but are not the authoritative domain audit. Workflow ID, commit/ref, environment, and domain run IDs provide correlation.

## 20. CI/CD

Pull requests run relevant linting, type checks, Python checks, unit tests, migration validation, and security checks. Required failures block merge. Exact tools are selected in Phase 0.

## 21. Deployment

Vercel hosts Next.js/Application API. Supabase hosts PostgreSQL/services. Python initially runs in GitHub Actions. A dedicated worker is future-only and requires measured need.

## 22. AI Architecture

AI Analyst and Assistant use only §10.4 AI Tool Layer and structured FootCap results. They distinguish source facts, model output, interpretation, and uncertainty. They have no arbitrary SQL, unrestricted database access, or authority to create/alter official predictions.

## 23. Change Logger

### 23.1 Git audit

Git is authoritative for versioned, committed changes: timestamp, branch, commit, author, files, insertions, deletions, status. It is not a forensic record of transient working-tree edits.

### 23.2 Attribution

Best-effort automatic attribution values are `human`, `codex`, `claude`, and `unknown`. ChatGPT is not an automatic attribution value because it does not directly modify filesystem/Git in this workflow. If Codex applies a change after discussion with ChatGPT, attribution is `codex`. Without reliable metadata it is `unknown`; attribution is never forensic proof.

## 24. Testing Strategy

Unit tests cover features/model/temporal/API/provider parsing. Integration tests cover repositories, migrations, adapter, API, jobs. Temporal tests cover future exclusion, verified availability, and declared classification. Model tests cover distributions, determinism, metrics, baselines. Contract tests cover provenance, official selection, job dependencies, API/AI visibility.

## 25. Security Principles

`Client → Application API → application authorization → Supabase grants → RLS → PostgreSQL`. Secrets are never committed. Backend credentials are server-side. Raw data, artifacts, snapshots, and job metadata are not client-accessible.

## 26. Performance Principles

V1 prioritizes correctness and simplicity: indexed queries, stable offset pagination, batch ingestion, controlled concurrency, database-backed locks, and caching only after measurement.

## 27. MVP Boundaries

V1 excludes microservices, dedicated AI microservices, Flutter implementation, live prediction infrastructure, advanced ensembles, subscriptions, social features, personalized AI memory, Kubernetes, Redis/Celery, Airflow, n8n core infrastructure, and DigitalOcean worker infrastructure.

## 28. First Vertical Slice

`API-Football → historical ingestion/raw provenance → validation/normalization → Supabase → point-in-time Feature Snapshot → Dixon-Coles → rolling Event-Time Safe backtest → Model Run provenance → read-only Application API`.

The first goal is a reproducible, temporal-safe statistical core, not a dashboard.

## 29. Phase 0

### 29.1 Foundation

Establish pnpm/tooling, Python environment, lint/type/test tooling, CI, Supabase environment strategy, secrets, Change Logger foundation, workflow documentation, temporal/model contract tests, and provider adapter skeleton.

### 29.2 Minimum schema

Phase 0 migrations create only schema needed for contract tests and vertical-slice foundations: source/domain entities; stable/provider identifiers; core temporal fields/classification; raw snapshot/ingestion identities; dataset, Feature Run/Snapshot, training/artifact, prediction run/prediction, backtest run/fold identities; and minimum unique/foreign-key constraints.

### 29.3 Full physical schema

The full physical schema remains open. Advanced indexes, optimization, optional derived tables, exhaustive endpoint support, and unneeded details are not frozen. Phase 0 has enough real schema for executable contracts, not the whole final database.

## 30. Architectural Decision Records

```text
ADR-001 — Modular Monolith for V1
ADR-002 — Point-in-Time Temporal Data Model
ADR-003 — Model Run and Prediction Run Provenance
ADR-004 — REST Application API V1
ADR-005 — Supabase Security and RLS Model
ADR-006 — GitHub Actions + Python Job Architecture
ADR-007 — Change Logger Two-Tier Attribution
ADR-008 — Event-Time Safe vs Knowledge-Time Verified Backtesting
ADR-009 — Cross-Language Contract Strategy (Phase 0 decision)
```

Each ADR records context, decision, alternatives, consequences, and status. ADR-009 does not mandate technology.

## 31. Open Architectural Decisions

1. Physical PostgreSQL details beyond Phase 0 minimum schema.
2. Source-fact correction/version policy and immutable dataset reconstruction.
3. Exact `source_available_at` evidence metadata/provider rules; §5 semantics are fixed.
4. API-Football endpoint coverage and polling schedule.
5. Exact Dixon-Coles V1 feature set.
6. Model artifact storage mechanism.
7. Authentication UX for future accounts.
8. Conservative production schedules after measurement.
9. Cross-language contracts for TypeScript, Python, future Flutter. Phase 0 may select OpenAPI or JSON Schema with generated TypeScript types and Python validation/models; no technology is mandatory.
10. Allowed filters and stable sorts per collection endpoint.

## 32. Approved Architecture Summary

| Area | V1.1 decision |
|---|---|
| Architecture | Modular monolith |
| Web/API | Next.js, REST + JSON, `/api/v1` |
| Database | Supabase PostgreSQL; RLS + application authorization |
| Statistical engine | One Python Engine |
| Model | Dixon-Coles baseline |
| Temporal model | Point-in-time; Event-Time Safe or Knowledge-Time Verified |
| Provenance | Dataset → Feature Snapshot → Training → Artifact → Prediction Run → Prediction |
| Official prediction | published, non-superseded PRODUCTION only |
| AI | Tool Layer → Application Service Layer; no SQL/direct DB |
| Scheduler | GitHub Actions initially |
| Change logging | Git audit + best-effort human/codex/claude/unknown |

## 33. Architecture Invariants

1. Official probabilities originate from model pipeline, never LLM.
2. Predictions are point-in-time constrained and declare classification.
3. Historical provider availability is never fabricated.
4. Completed feature/model/prediction/backtest records are immutable.
5. Official predictions trace to exact provenance chain.
6. Only published PRODUCTION predictions can be official singular public predictions.
7. Clients consume domain APIs, not database tables.
8. AI has no arbitrary SQL/database access and cannot misrepresent non-production output.
9. Browser clients cannot mutate authoritative football data.
10. Backend credentials never reach clients.
11. Scheduler logic is separate from Python domain logic.
12. Change attribution is never falsely asserted.
13. New infrastructure requires actual need or measured bottleneck.

## 34. Next Step

Phase 0 may begin with tooling, minimum migrations, CI, Change Logger foundation, temporal/model contract tests, and provider adapter skeleton. Feature development begins only after this foundation is green.

## 35. V1.1 Change Summary

- Unified `source_available_at`; clarified Event-Time Safe and Knowledge-Time Verified; fixed timestamp semantics.
- Added Feature Run and immutable Feature Snapshot provenance.
- Made Prediction Run reference Training Run, artifact, Feature Snapshot, and hash.
- Defined deterministic official PRODUCTION publication and public visibility.
- Added Supabase actor/credential matrix without claiming separate DB identities.
- Defined AI Tool Layer routing and equivalent provenance/publication protection.
- Added common job provenance, dependencies, and feature-job tracking.
- Restricted automatic attribution to human, codex, claude, unknown.
- Added Phase 0 minimum schema, pagination rules, cross-language decision, and fold cardinality.
