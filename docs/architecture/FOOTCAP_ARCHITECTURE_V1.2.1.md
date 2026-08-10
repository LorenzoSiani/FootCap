Exit code: 0
Wall time: 1.3 seconds
Output:
Exit code: 0
Wall time: 1.2 seconds
Output:
# FootCap Architecture V1.2.1

**Status:** Candidate Architecture Baseline  
**Supersedes:** FOOTCAP_ARCHITECTURE_V1.2.md

## 1. Purpose

V1.2 preserves the approved modular monolith: Next.js, one Python Engine, Supabase/PostgreSQL, REST + JSON, GitHub Actions, Dixon-Coles, and the AI Tool Layer. It resolves only remaining contract ambiguities. It introduces no microservices, new infrastructure, or product features.

## 2. Architectural Principles

### 2.1 Data → Model → Probability → AI → User

Official probabilities originate only in the statistical pipeline. AI interprets structured FootCap data and cannot invent or alter official probabilities.

### 2.2 Modular monolith first

Logical boundaries are mandatory; independent deployments are not.

### 2.3 Python owns statistical intelligence

Python owns ingestion, normalization, features, model fitting, prediction, backtesting, and evaluation. Frontend and AI do not reproduce statistical logic.

### 2.4 Application API is the client contract

Web, AI Tool Layer, and future Flutter consume domain-oriented Application API/service contracts, never database tables.

### 2.5 Temporal correctness and reproducibility

Every prediction has a cutoff and temporal_classification. Every official execution is traceable to dataset, training feature set, prediction feature snapshot, code, dependency lock, configuration, and artifact.

## 3. System Overview

API-Football flows through the Python Engine to Supabase/PostgreSQL. Next.js hosts the web, Application API/BFF, Application Service Layer, and AI Tool Layer. GitHub Actions is CI and initial job scheduler. GitHub is source control and authoritative audit for committed changes.

No DigitalOcean, Redis, Celery, Kubernetes, Airflow, or n8n is required for V1.

## 4. Repository Architecture

The monorepo remains apps/web, engine, packages/contracts, packages/config, supabase/migrations, tests, tools/change-logger, docs, logs, and GitHub workflows. Exact folders may evolve without changing ownership boundaries.

## 5. Temporal Data Model

### 5.1 Canonical fields

- event_at: underlying football event time.
- requested_at: FootCap request time.
- received_at: FootCap provider-response time.
- ingested_at: FootCap persistence time.
- source_available_at: earliest availability time FootCap can support with evidence for a source fact.

source_observed_at is not a V1 term and must not be used as an alternative to source_available_at.

### 5.2 V1 timestamp convention

- Timestamps are timezone-aware UTC instants.
- V1 precision is milliseconds. Finer input is normalized without changing instant; coarser known precision is retained in provenance metadata.
- Prior event eligibility requires event_at < prediction_cutoff.
- Verified availability eligibility requires source_available_at <= prediction_cutoff.
- source_available_at is nullable only for UNKNOWN. UNKNOWN is never an earlier instant and cannot satisfy Knowledge-Time Verified.
- FootCap-collected raw snapshots require requested_at, received_at, and ingested_at. A missing event_at is explicit and cannot satisfy a rule requiring event time.

### 5.3 Material source fact

A material source fact is every source fact actually consumed by the feature calculation for the applicable prediction_cutoff.

Materiality is determined by recorded feature-generation inputs for the Training Feature Set or Prediction Feature Snapshot; it is not a manual or retrospective judgment. Stored facts not consumed are not material for that result.

### 5.4 Source availability policy

Historical API-Football availability may be UNKNOWN and is never fabricated. For prospective collection, raw snapshots establish FootCap evidence. For a live-collected fact, source_available_at equals received_at unless documented evidence supports another instant; evidence and rationale are retained.

### 5.5 Backtest classes and invariant

Event-Time Safe uses event_at < prediction_cutoff to exclude future events. source_available_at may be UNKNOWN historically. It records Event-Time Safe as temporal_classification and must never be represented as Knowledge-Time Verified.

Knowledge-Time Verified requires event_at < prediction_cutoff where relevant and every material source fact to meet source_available_at <= prediction_cutoff.

Every Dataset, Training Feature Set, Prediction Feature Snapshot, Training Run, Prediction Run, Backtest Run, and Backtest Fold records temporal_classification. A result cannot be upgraded without supporting availability evidence.

### 5.6 Raw snapshots and features

Raw snapshots retain provider, endpoint, parameters, request/receive times, status, response hash, payload, ingestion run ID, and availability evidence. Feature generation is parameterized by cutoff and temporal_classification; it cannot silently use current state.

## 6. Data Architecture

Source/domain facts are competitions, seasons, teams, matches, events, and statistics. Derived data includes form, strengths, home advantage, and features.

Conceptual entities include datasets, feature_runs, training_feature_sets, prediction_feature_snapshots, ingestion_runs, raw_provider_responses, training_runs, model_artifacts, prediction_runs, predictions, backtest_runs, and backtest_folds.

A normalized current view may be updated idempotently, but data used by a completed dataset or feature object remains reconstructible and immutable. Source-fact correction/version policy remains open before substantive ingestion.

## 7. Model Run Contract

### 7.1 Provenance chain

Dataset → Training Feature Set → Training Run → Model Artifact → Prediction Feature Snapshot → Prediction Run → Prediction.

Completed records do not mutate provenance; corrections and reruns create versioned records.

### 7.2 Dataset identity

Dataset identity includes dataset_id, dataset_version, competition, seasons, source, snapshot_hash, schema_version, temporal_classification, and created_at. It deterministically identifies source-data selection.

### 7.3 Feature logic and Feature Run

feature_version identifies feature-generation logic only. It is not a training matrix or prediction input identifier.

Every feature execution creates a feature_run, linked to common Job Run provenance, with source selection, cutoff or cutoff range, feature_version, temporal_classification, material source-fact consumption record, status, and metadata.

Feature generation may be internal to training or prediction. A separate features workflow is not required, but feature_run provenance is mandatory whenever features are generated.

### 7.4 Training Feature Set

A Training Feature Set is the full immutable collection of features consumed by one Training Run. It may include many matches, dates, and cutoffs.

It records training_feature_set_id, training_feature_set_hash, dataset ID/version, feature_version, training-window start/end, temporal_classification, feature_run_id, and created_at. Its hash identifies exact normalized fitting content and its material source facts are the recorded consumed inputs.

### 7.5 Training Run and Model Artifact

Training Run records model name/version, dataset ID/version, training_feature_set_id, training_feature_set_hash, feature_version, training window, cutoff policy, temporal_classification, parameters, seed, code commit, dependency-lock hash, status, and creation time.

A successful run produces immutable artifact_id, training_run_id, storage reference, checksum, format, size, and creation time. Lockfile/runtime is recoverable from recorded provenance; seed is explicit and null only when randomness does not apply.

### 7.6 Prediction Feature Snapshot

A Prediction Feature Snapshot is the full immutable feature input consumed for one prediction context: match_id plus prediction_cutoff.

It records prediction_feature_snapshot_id, prediction_feature_snapshot_hash, dataset ID/version, feature_version, match_id, prediction_cutoff, temporal_classification, feature_run_id, and created_at. Its hash identifies exact normalized inference input; its consumed material source facts determine verification. It is distinct from a Training Feature Set even if generated by the same logic.

### 7.7 Prediction Run

Prediction Run records training_run_id, artifact_id, match_id, prediction_cutoff, prediction_horizon, prediction_feature_snapshot_id, prediction_feature_snapshot_hash, feature_version, evaluation_context, temporal_classification, status, and created_at.

The artifact belongs to the stated Training Run; the snapshot ID/hash matches the input used for match/cutoff.

Evaluation contexts are:

- PRODUCTION: candidate or user-facing output.
- BACKTEST: controlled historical evaluation; never official current prediction.
- EXPERIMENT: research/validation; never official.

V1 has exactly one canonical prediction_horizon: PRE_MATCH. PRE_MATCH is the official prediction generated before kickoff and valid for the pre-match context. T-24h, T-6h, T-1h, live, and other horizons are not V1 values.

### 7.8 Prediction publication

V1 output is home/draw/away probability forming a valid distribution.

`publication_state` applies only to PRODUCTION Prediction records and has exactly these values:

- **DRAFT:** a persistent internal candidate PRODUCTION Prediction. It is generated and persisted before official publication, is not official, is not exposed by public APIs, cannot be used as a fallback, and can transition only to PUBLISHED.
- **PUBLISHED:** the current official PRODUCTION prediction for its match and PRE_MATCH horizon.
- **SUPERSEDED:** a previously PUBLISHED PRODUCTION prediction replaced by a later official prediction; it remains readable only through the PRODUCTION history endpoint.
- **WITHDRAWN:** a previously PUBLISHED PRODUCTION prediction withdrawn because its match was postponed, cancelled, or is no longer valid for the PRE_MATCH context; it remains readable only through the PRODUCTION history endpoint.

BACKTEST and EXPERIMENT records do not enter the public publication-state lifecycle. Their execution/result status remains provenance/internal metadata and they can never be selected as official.

Every Prediction has an immutable `prediction_run_id`. A PRODUCTION replacement also has `supersedes_prediction_id`, which points to its immediate prior official Prediction. The link must remain within the same `match_id`, `prediction_horizon = PRE_MATCH`, and `evaluation_context = PRODUCTION`; it must not create cycles, branches, or cross-match/context links.

Only PUBLISHED PRODUCTION is official. For each match_id plus PRE_MATCH plus PRODUCTION, at most one PUBLISHED prediction exists.

The only valid publication-state transitions are:

```text
DRAFT → PUBLISHED
PUBLISHED → SUPERSEDED
PUBLISHED → WITHDRAWN
```

No other transition is implicitly permitted.

Draft creation and initial publication are distinct operations. First, a new PRODUCTION Prediction is created and persisted in DRAFT. Validation checks may then run. Publication is a separate atomic DRAFT to PUBLISHED lifecycle operation that verifies the uniqueness rule in the same operation.

A replacement begins with an old PUBLISHED Prediction and a persisted new DRAFT Prediction. One atomic database operation validates lineage and uniqueness, transitions the old PUBLISHED Prediction to SUPERSEDED, and transitions the new DRAFT Prediction to PUBLISHED. All changes commit together or roll back together. A committed replacement cannot expose two PUBLISHED Predictions, a new PUBLISHED Prediction without supersession lineage, or an old SUPERSEDED Prediction without its new PUBLISHED successor.

For every match_id plus prediction_horizon = PRE_MATCH plus evaluation_context = PRODUCTION, the count of PUBLISHED Predictions is 0 or 1 and can never exceed 1. Zero is valid before first publication, after PUBLISHED to WITHDRAWN, and whenever no official prediction exists. This rule is enforced consistently by the database uniqueness constraint, publication lifecycle operation, official endpoint, history endpoint, and contract tests.

If a PUBLISHED prediction becomes invalid because the match is postponed, cancelled, or no longer valid for PRE_MATCH, the authorized lifecycle operation transitions it from PUBLISHED to WITHDRAWN. The Prediction is not deleted and remains available through PRODUCTION history with its original provenance. A prediction for a later or rescheduled context must be a new Prediction and Prediction Run; the withdrawn Prediction provenance is never retroactively changed.

Prediction provenance is immutable. `publication_state` is the only Prediction lifecycle field authorized to change, and only through the transitions above. Supersession is reconstructed through IDs, never timestamps alone.

### 7.9 Reproducibility invariant

Prediction provenance is immutable. publication_state is the sole lifecycle field authorized to change, and only through the explicitly defined lifecycle transitions in §7.8. No other Prediction mutation is permitted. Completed feature, training, prediction, and backtest provenance; Training Feature Sets; Prediction Feature Snapshots; and artifacts are immutable. Every prediction traces to exact Dataset, Training Feature Set, Training Run, artifact, Prediction Feature Snapshot/hash, code, dependencies, configuration, and temporal_classification.

No inference object is implicitly reused as a training object: a Prediction Feature Snapshot is always distinct from a Training Feature Set. The persisted lineage is explicit: Training Run references its Training Feature Set; Model Artifact references its Training Run; Prediction Run references both its Model Artifact and Prediction Feature Snapshot; Prediction references its Prediction Run. Each reference is immutable after completion.

## 8. Prediction Architecture

Dixon-Coles is the V1 official 1X2 probability source. Future models preserve this contract. AI cannot alter official probabilities.

## 9. Backtesting Architecture

V1 rolling-origin relationship is:

Backtest Run → Backtest Fold → Training Feature Set → Training Run → Model Artifact → Prediction Feature Snapshot(s) → BACKTEST Prediction Run(s).

Each fold records training/prediction cutoff(s), temporal_classification, training context, linked feature set/run/artifact/snapshots/prediction runs/predictions, outcomes, metrics, and baseline comparison. Each persisted link follows the lineage in §7.9; no relationship is inferred from matching timestamps or model names. Historical benchmarks are Event-Time Safe unless availability is demonstrated.

## 10. Application API Architecture

### 10.1 Protocol

V1 uses REST + JSON under /api/v1/. No GraphQL or gRPC. Target reads cover competitions, matches, events/statistics, predictions, teams, models, and backtests. The first vertical slice needs match list/detail, singular prediction, model detail, and backtest detail.

### 10.2 Official prediction endpoint

GET /api/v1/matches/:id/prediction returns exclusively:

- evaluation_context = PRODUCTION
- prediction_horizon = PRE_MATCH
- publication_state = PUBLISHED

The endpoint is deterministic because §7.8 permits at most one matching record. If none exists, it returns the normal error contract with a documented prediction-not-available error code. It never predicts on demand and never falls back to BACKTEST or EXPERIMENT.

### 10.3 Production prediction history endpoint

GET /api/v1/matches/:id/predictions returns only evaluation_context = PRODUCTION. It may include PUBLISHED, SUPERSEDED, and WITHDRAWN Predictions to show public PRODUCTION history; every record exposes publication_state and supersedes_prediction_id where present. DRAFT is internal and is never returned. The endpoint never returns BACKTEST or EXPERIMENT.

The public API provides no arbitrary historical cutoff generation and never presents Event-Time Safe backtest output as official. Exposed methodology/performance information retains temporal_classification.

### 10.4 Errors, IDs, pagination

Errors use the normal V1 shape containing error code, message, and request_id. Every request has a traceable ID. Collections use offset pagination with mandatory stable ordering; permitted filters and sorts are defined per endpoint before implementation.

### 10.5 AI Tool Layer

AI → AI Tool Layer → Application Service Layer → data access → Supabase.

Tools are semantic operations such as get_match, get_prediction, get_team_form, get_team_statistics, compare_teams, and get_model_info. They are not arbitrary SQL or direct database clients.

Tool outputs enforce the same publication, temporal, horizon, and provenance protection as public API. AI cannot obtain or present BACKTEST/EXPERIMENT as PRODUCTION, cannot fabricate a missing official prediction, and cannot bypass PRE_MATCH selection.

## 11. Supabase Security Architecture

RLS applies to client-exposed relations and complements Application API authorization. Raw data, artifacts, Training Feature Sets, Prediction Feature Snapshots, and job metadata are never browser-accessible.

| Actor | Credential | Schema | Read | Write | Restrictions |
|---|---|---|---|---|---|
| anonymous browser | publishable key / no session | exposed public domain if directly exposed | policy-approved public reads | none | no authoritative writes; API remains contract |
| authenticated user | publishable key + Auth session | public domain and own user tables | public reads and own rows | own user rows only | auth.uid(); no football/model/raw writes |
| Next.js server | backend-only secret key | public/private needed by Application Service Layer | domain and needed provenance | server-authorized operations | never client-delivered; API/tool policy |
| Python Engine | backend-only secret key | public/private needed for jobs | source/provenance/model inputs | ingestion/features/runs/artifacts/predictions through repositories | statistical writes, not client authorization |
| admin/internal operator | controlled operator credential | operational scope | operational reads | explicitly authorized writes | deliberate/logged; never browser-delivered |

Next.js and Python are trusted backend components with different responsibilities, not automatically distinct PostgreSQL identities. The Write-column differences are application-level responsibility and repository boundaries, not distinct PostgreSQL or RLS identities. V1 uses backend credentials and does not introduce separate PostgreSQL roles unless later required. RLS remains the barrier for exposed clients.

Before migrations, direct browser-readable relations and RLS policies are explicit. Browser access never substitutes for Application API. Browser users cannot write authoritative football data, predictions, model runs, or raw data. Views, RPC, and SECURITY DEFINER require security review.

## 12. Python Engine Architecture

One Python package contains CLI, ingestion, features, models, prediction, backtest, data, repositories, and validation. The same CLI runs locally and in automation. Provider calls remain behind one adapter owning HTTP, timeouts, retries, rate limits, error mapping, and request/response logging.

## 13. Python Job Architecture

V1 job types are ingestion, features, training, prediction, and backtest. Every execution records job_type, status, started_at, finished_at, trigger, git_commit, git_ref, environment, workflow_run_id, error_summary, metadata.

The common Job Run links to ingestion_run, feature_run, training_run, prediction_run, or backtest_run. Specific records add methodology fields but never omit execution provenance.

Ingestion is idempotent where possible and uses PENDING, RUNNING, COMPLETED, PARTIAL, FAILED, CANCELLED.

Mandatory downstream policy:

- COMPLETED: downstream allowed.
- PARTIAL: allowed only if explicit job/data policy declares input sufficient.
- FAILED: downstream blocked.
- CANCELLED: downstream blocked.

Downstream runs record upstream IDs and PARTIAL acceptance policy. They cannot infer readiness from current tables. PostgreSQL advisory locks or equivalent database-backed locking prevent mutually exclusive overlap.

## 14. Feature Job

Feature generation consumes temporally eligible normalized data, cutoff or training range, feature logic version, and temporal_classification. It creates feature_run plus the applicable immutable Training Feature Set or Prediction Feature Snapshot, never silently depending on current time.

## 15. Training Job

Training consumes dataset, Training Feature Set, model version, training window, parameters; it creates Training Run and Model Artifact. Failed runs remain auditable and cannot be promoted.

## 16. Prediction Job

Prediction consumes match, artifact, Prediction Feature Snapshot, cutoff, PRE_MATCH horizon, and evaluation context; it creates traceable Prediction Run and Prediction without mutating artifact.

## 17. Backtest Job

Backtests are controlled engine operations, never arbitrary public API operations, and preserve §9 provenance.

## 18. Job Orchestration

GitHub Actions triggers CLI, provides approved environment/secrets, captures logs, and reports status; it has no FootCap domain logic. Expected workflows are CI, ingestion, training, prediction, and backtest. A separate features workflow is optional because generation may be internal; feature_run provenance is mandatory.

## 19. Job Observability

Common Job Run provenance is the authoritative application execution record. GitHub Actions logs aid diagnosis but are not the authoritative domain audit. Workflow ID, commit/ref, environment, and domain run IDs provide correlation.

## 20. CI/CD

Pull requests run relevant linting, type checks, Python checks, unit tests, migration validation, and security checks. Required failures block merge. Exact tools are selected in Phase 0.

## 21. Deployment

Vercel hosts Next.js/Application API. Supabase hosts PostgreSQL/services. Python initially runs in GitHub Actions. A dedicated worker is future-only and requires measured need.

## 22. AI Architecture

AI Analyst and Assistant use only the AI Tool Layer and structured FootCap results. They distinguish source facts, model output, interpretation, uncertainty; they have no arbitrary SQL, unrestricted database access, or authority to create/alter official predictions.

## 23. Change Logger

Git is authoritative for versioned, committed changes and is not forensic evidence for transient edits.

Automatic attribution is best effort and only uses human, codex, claude, unknown:

- codex requires positive Codex attribution evidence;
- claude requires positive Claude Code attribution evidence;
- human requires positive evidence of human-applied modification and is never fallback for an undetected agent;
- unknown is required when origin cannot be established with sufficient certainty.

ChatGPT is not automatic attribution because it does not directly modify filesystem/Git in this workflow. If Codex applies a change after discussion with ChatGPT, attribution is codex.

Better unknown than a false attribution.

## 24. Testing Strategy

Unit tests cover features/model/temporal/API/provider parsing. Integration tests cover repositories, migrations, adapter, API, jobs. Temporal tests cover future exclusion, material-source availability, temporal_classification. Model tests cover distributions, determinism, metrics, baselines. Contract tests cover Training Feature Set/Prediction Feature Snapshot provenance, official selection, supersession, dependencies, API/AI visibility.

## 25. Security Principles

Client → Application API → application authorization → Supabase grants → RLS → PostgreSQL. Secrets are never committed. Backend credentials are server-side. Raw data, artifacts, feature objects, and job metadata are not client-accessible.

## 26. Performance Principles

V1 prioritizes correctness and simplicity: indexed queries, stable offset pagination, batch ingestion, controlled concurrency, database-backed locks, caching only after measurement.

## 27. MVP Boundaries

V1 excludes microservices, dedicated AI microservices, Flutter implementation, live prediction infrastructure, advanced ensembles, subscriptions, social features, personalized AI memory, Kubernetes, Redis/Celery, Airflow, n8n core infrastructure, and DigitalOcean worker infrastructure.

## 28. First Vertical Slice

API-Football → historical ingestion/raw provenance → validation/normalization → Supabase → Training Feature Set / Prediction Feature Snapshot → Dixon-Coles → rolling Event-Time Safe backtest → Model Run provenance → read-only Application API.

The first goal is a reproducible temporal-safe statistical core, not a dashboard.

## 29. Phase 0

Phase 0 establishes tooling, Python environment, lint/type/test tooling, CI, Supabase environments, secrets, Change Logger foundation, workflow documentation, temporal/model contract tests, provider adapter skeleton.

Minimum migrations cover source/domain entities, stable/provider identifiers, temporal fields and temporal_classification, raw snapshot/ingestion identities, dataset, feature run, Training Feature Set, Prediction Feature Snapshot, training/artifact, prediction/prediction run, backtest/fold identities, plus minimum uniqueness and foreign-key constraints.

The full physical schema remains open: advanced indexes, optimization, optional derived tables, exhaustive endpoints, and unneeded details are not frozen. Phase 0 has enough schema for executable contracts, not the entire final database.

## 30. Architectural Decision Records

- ADR-001: Modular Monolith for V1.
- ADR-002: Point-in-Time Temporal Data Model and temporal_classification.
- ADR-003: Model Run Contract including Training Feature Set, Prediction Feature Snapshot, Model Artifact, Prediction Run, provenance chain.
- ADR-004: REST Application API V1.
- ADR-005: Supabase Security and RLS Model.
- ADR-006: GitHub Actions + Python Job Architecture.
- ADR-007: Change Logger Two-Tier Attribution.
- ADR-008: Event-Time Safe vs Knowledge-Time Verified Backtesting.
- ADR-009: Cross-Language Contract Strategy, Phase 0 decision.

## 31. Open Architectural Decisions

1. Physical PostgreSQL columns, indexes, and optimization beyond Phase 0 minimum schema.
2. Source-fact correction/version policy and immutable dataset reconstruction.
3. Exact source_available_at evidence metadata/provider-specific population rules; §5 semantics and material-source definition are fixed.
4. API-Football endpoint coverage and polling schedule.
5. Exact Dixon-Coles V1 feature set.
6. Model artifact storage mechanism.
7. Authentication UX for future accounts.
8. Conservative production schedules after measurement.
9. Cross-language contracts for TypeScript, Python, future Flutter. Phase 0 may select OpenAPI or JSON Schema with generated TypeScript types and Python validation/models; no technology is mandatory.
10. Allowed filters and stable sorts per collection endpoint.

## 32. Approved Architecture Summary

| Area | V1.2.1 decision |
|---|---|
| Architecture | Modular monolith |
| Web/API | Next.js, REST + JSON, /api/v1 |
| Database | Supabase PostgreSQL; RLS + application authorization |
| Statistical engine | One Python Engine |
| Model | Dixon-Coles baseline |
| Temporal model | Point-in-time; Event-Time Safe or Knowledge-Time Verified |
| Feature provenance | Training Feature Set distinct from Prediction Feature Snapshot |
| Prediction horizon | PRE_MATCH only |
| Official prediction | one PUBLISHED PRODUCTION PRE_MATCH record per match |
| AI | Tool Layer → Application Service Layer; no SQL/direct DB |
| Scheduler | GitHub Actions initially |
| Change logging | Git audit + best-effort human/codex/claude/unknown |

## 33. Architecture Invariants

1. Official probabilities originate from model pipeline, never LLM.
2. Predictions are point-in-time constrained and declare temporal_classification.
3. Historical provider availability is never fabricated.
4. Knowledge-Time Verified requires each material source fact available at/before cutoff.
5. Prediction provenance is immutable; publication_state is the sole lifecycle field permitted to change through defined transitions.
6. Every prediction traces Dataset → Training Feature Set → Training Run → Artifact → Prediction Feature Snapshot → Prediction Run → Prediction.
7. Only PUBLISHED PRODUCTION PRE_MATCH predictions can be official singular public predictions.
8. BACKTEST and EXPERIMENT cannot be exposed or represented as PRODUCTION.
9. Clients consume domain APIs, not database tables.
10. AI has no arbitrary SQL/database access and cannot misrepresent non-production output.
11. Browser clients cannot mutate authoritative football data.
12. Backend credentials never reach clients.
13. Scheduler logic is separate from Python domain logic.
14. Change attribution is never falsely asserted.
15. New infrastructure requires actual need or measured bottleneck.

## 34. Next Step

Phase 0 may begin with tooling, minimum migrations, CI, Change Logger foundation, temporal/model contract tests, and provider adapter skeleton. Feature development begins only after this foundation is green.

## 35. V1.2 Change Summary

- Distinguished Training Feature Set from Prediction Feature Snapshot and immutable hashes.
- Defined material source fact as the testable Knowledge-Time Verified basis.
- Set PRE_MATCH as the only V1 horizon.
- Made official prediction API deterministic and defined no-prediction behavior.
- Defined PRODUCTION-only prediction history and supersedes_prediction_id.
- Standardized temporal_classification naming.
- Clarified Supabase Write boundaries as application-level, not separate RLS identities.
- Clarified positive-only human/Codex/Claude attribution and unknown fallback.

## 36. V1.2.1 Change Summary

- Clarified DRAFT as a persistent internal candidate state.
- Clarified the initial publication lifecycle: persistent DRAFT, validation, then atomic DRAFT → PUBLISHED.
- Clarified the atomic replacement lifecycle: old PUBLISHED → SUPERSEDED and new DRAFT → PUBLISHED.
- Clarified the zero-or-one PUBLISHED rule.
- Restricted public prediction history to PUBLISHED, SUPERSEDED, and WITHDRAWN.
- Clarified withdrawal semantics and preserved withdrawn/superseded records for historical provenance.
- Updated the immutability invariant: Prediction provenance is immutable and publication_state is the sole mutable lifecycle field.
- Corrected the Backtest cross-reference to §7.9.
- Corrected document version metadata.
- Corrected UTF-8 encoding.


