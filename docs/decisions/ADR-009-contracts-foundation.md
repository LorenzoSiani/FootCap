# ADR-009: Contracts Foundation — Phase 0 Implementation Decisions

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.3.2

**Relation to the Architecture Baseline:** This ADR is an implementation decision for Phase 0 and does **NOT** modify `FOOTCAP_ARCHITECTURE_V1.2.1.md`. The Architecture Baseline remains FROZEN. Nothing in this document overrides, reopens, or reinterprets any invariant, contract, or classification defined in the baseline. Where this ADR makes a choice, it is a choice among options the baseline deliberately left open (see ADR-009 in the baseline's own ADR index, §30, and the corresponding open item in §31.9), not a new architectural decision.

---

## Context

`FOOTCAP_ARCHITECTURE_V1.2.1.md` establishes the modular monolith, the temporal data model, the Model Run Contract, the frozen prediction lifecycle, and the cross-language boundary between `packages/contracts/` (shared) and `engine/src/footcap_engine/contracts/` (Python-internal), but explicitly leaves the following open for Phase 0:

- the concrete cross-language contract technology (§31.9: "Phase 0 may select OpenAPI or JSON Schema with generated TypeScript types and Python validation/models; no technology is mandatory");
- the physical schema and several field-level details beyond the Phase 0 minimum (§31.1, §31.3, §31.10);
- assorted operational details not addressed by the baseline at all (job trigger/environment vocabularies, dirty-tree run handling, provider-to-domain ID mapping).

A read-only design review (Task 0.3.1) examined the minimum V1 contracts required for temporal correctness, run provenance, feature provenance, model/prediction provenance, the prediction lifecycle, and backtesting, and surfaced a specific set of implementation-level questions that needed a decision before contract files could be written. This ADR records the decisions made in response to that review.

No new entities, fields, or invariants are introduced. This ADR only resolves *how* the already-defined baseline concepts are represented, versioned, and serialized, and closes a small number of gaps the baseline left unaddressed by design.

---

## Decision

Adopt the thirteen implementation decisions below for the Contracts Foundation. `packages/contracts/` becomes the single source of truth for shared cross-language shapes; `engine/src/footcap_engine/contracts/` holds Python-internal representations only. No contract files, code, migrations, or dependencies are introduced by this ADR — it records decisions to be executed in a subsequent Phase 0 task.

### 1. Shared contract format: JSON Schema

The shared contract format for V1 is JSON Schema. It is the minimal tool for shape/validation agreement across languages without prescribing HTTP/endpoint semantics prematurely, and it composes forward into OpenAPI later if needed (OpenAPI 3.1 consumes JSON Schema natively), so it does not foreclose that option once the Application API's exact endpoint surface is finalized (§31.10, still open).

### 2. Source of truth: `packages/contracts/*.schema.json`

The authored `.schema.json` files under `packages/contracts/` are the canonical definition of every shared shape (the enums and entities identified in the Task 0.3.1 review: `TemporalClassification`, `EvaluationContext`, `PredictionHorizon`, `PublicationState`, `Prediction`, and the still-to-be-scoped `ModelInfo`/`BacktestSummary` public descriptors). No other file, in either language, is authoritative for these shapes.

### 3. Generated representations

TypeScript types and Python/Pydantic representations are build-time generated and/or validated from the JSON Schema source — never hand-authored a second time. Generated output is a build artifact, not a parallel source of truth.

### 4. No duplicate hand-authored contracts

`engine/src/footcap_engine/contracts/` contains Python-internal representations only (the internal provenance entities identified in Task 0.3.1: Dataset, FeatureRun, TrainingFeatureSet, PredictionFeatureSnapshot, TrainingRun, ModelArtifact, PredictionRun, BacktestRun, BacktestFold, JobRun, TemporalFact). It must not redefine or fork the shared enums/entities that live in `packages/contracts/`; where it needs those values, it consumes the generated Python representation.

### 5. Contract versioning

Git-versioned schema files are sufficient for V1. No runtime `contract_version` field is embedded in serialized payloads, and no schema registry is introduced. V1 has a single deployment cadence (Python Engine and the Next.js server ship from the same monorepo together); this decision is scoped to that condition (see Future Reconsideration Triggers).

### 6. Timestamp serialization

Canonical wire representation is ISO 8601, timezone-aware, UTC (e.g. `...Z` offset). This satisfies the baseline's requirement that timestamps be "timezone-aware UTC instants" (§5.2) with a concrete, language-neutral serialization; it does not change the underlying instant semantics already fixed by the baseline.

### 7. PredictionFeatureSnapshot cardinality

One immutable Prediction Feature Snapshot may be consumed by multiple Prediction Runs. This resolves the cardinality question raised in the Task 0.3.1 review without altering the baseline's requirement that a Prediction Feature Snapshot always remain distinct from, and never confused with, a Training Feature Set (§7.9).

### 8. BacktestRun

Backtest Run is a minimal top-level container (identity plus whatever aggregate fields are needed to back `GET /api/v1/backtests/:id`, TBD at schema-authoring time). Detailed execution/provenance content lives on Backtest Fold and the entities Backtest Fold links to, consistent with §9's fold-level field list.

### 9. JobRun trigger/environment

`trigger` and `environment` remain implementation-level strings in V1 rather than prematurely closed enums, since the baseline does not enumerate their vocabulary and no downstream policy (unlike `job_type`/`status`) is defined against a closed set of values for these two fields.

### 10. Git provenance

`git_commit` and `git_ref` are required for CI-triggered runs and may be nullable for local runs. A local run must never falsely represent dirty/uncommitted local state as fully reproducible; where these fields are null, the run's reproducibility guarantee (§7.9) is correspondingly weaker and must be treated as such by any consumer, not silently upgraded.

### 11. Match identity

FootCap `match_id` is provider-independent domain identity. External provider identifiers, including API-Football match IDs, are stored through provider-specific mappings and are never used as the domain identity itself. This keeps the data-provider replaceability goal (Master Brief §6/§9, baseline §2.3) intact at the identifier level.

### 12. UNKNOWN semantics

`source_available_at` must always be present as a field on records where it applies. `null` means UNKNOWN — this is the sole encoding of UNKNOWN for this field (§5.2: "nullable only for UNKNOWN"). A missing/omitted field is invalid/incomplete input, not an alternative way of expressing UNKNOWN, and must be rejected rather than interpreted.

### 13. temporal_classification

Persisted contract records must always contain exactly one of `EVENT_TIME_SAFE` or `KNOWLEDGE_TIME_VERIFIED`. No `PENDING`/`UNKNOWN`/`UNCLASSIFIED` state is introduced; classification is computed and persisted atomically at record creation, consistent with the baseline's two-value definition (§5.5).

---

## Consequences

- Every shared enum/entity has exactly one authored definition (`packages/contracts/*.schema.json`); Python and TypeScript representations are derived, removing the primary drift risk identified in the Task 0.3.1 review.
- A codegen step becomes part of the Phase 0 toolchain (JSON Schema → TypeScript, JSON Schema → Python/Pydantic); CI must be able to detect staleness between schema and generated output before this is safe to rely on — this is a follow-on Phase 0 task, not covered by this ADR.
- No schema registry or runtime version negotiation exists; upgrading a shared shape in a backward-incompatible way requires coordinated deployment of Python Engine and the Next.js server together, which is acceptable only as long as decision 5's single-deployment-cadence condition holds.
- `git_commit`/`git_ref` being nullable for local runs means reproducibility-completeness checks (Task 0.3.1 test plan item 8) must treat "local, unreproducible" as a valid but weaker-guarantee state, not an error condition to reject outright — downstream logic that assumes full reproducibility must check for this explicitly.
- `match_id` being provider-independent requires a provider-mapping table/mechanism to exist before ingestion can resolve API-Football matches to FootCap matches; this is a Phase 1/2 data-architecture consequence, not created by this ADR.
- `trigger`/`environment` being open strings in V1 means no compile-time/schema-time protection against typos in these two fields; this is an accepted, explicitly scoped trade-off, not an oversight.

---

## Rejected Alternatives

- **OpenAPI as the Phase 0 source of truth** — rejected for now because it couples the contract layer to endpoint/operation semantics (§31.10 filters/sorts, exact response envelopes) that are not yet decided; JSON Schema is the smaller, sufficient tool for the current need and does not preclude adopting OpenAPI once the endpoint surface stabilizes.
- **TypeScript-first contracts (hand-written TS, generate Python from it)** — rejected because it makes one language's tooling the source of truth for a cross-language boundary that must equally serve Python (producer of most of the data) and a future Flutter/Dart client; a language-neutral schema format is more appropriate than privileging one runtime.
- **A schema registry / runtime `contract_version` field** — rejected for V1 as premature: it solves a problem (independently-deployed, asynchronously-upgraded consumers) that does not exist yet under the current single-deployment-cadence model, and would add operational complexity the baseline's "new infrastructure requires actual need or measured bottleneck" invariant (§33.15) argues against.
- **Closed enums for `trigger`/`environment`** — rejected because the baseline defines no fixed vocabulary for these fields and no downstream policy depends on a closed set, unlike `job_type`/`status`; closing them now would be inventing an architectural decision the baseline left open.
- **Treating a missing `source_available_at` field as equivalent to UNKNOWN** — rejected because it conflates "the producer forgot to populate this field" (a defect) with "the producer explicitly asserts the value is unknown" (a valid, evidenced state); only an explicit `null` carries UNKNOWN semantics.
- **API-Football match ID as FootCap's domain `match_id`** — rejected because it would couple domain identity to a specific, potentially-replaceable data provider, contradicting the provider-replaceability goal already established in the Master Brief and baseline.

---

## Scope

This ADR governs only the Contracts Foundation implementation decisions listed above. It does not:

- define the actual JSON Schema files or their exact field-by-field content (a subsequent Phase 0 task);
- define the exact public response shape of `Prediction`, `ModelInfo`, or `BacktestSummary` (still open, per Task 0.3.1);
- define Backtest Run's exact field list beyond "minimal container" (decision 8 sets the principle, not the schema);
- change any invariant, entity, classification, or lifecycle rule defined in `FOOTCAP_ARCHITECTURE_V1.2.1.md`;
- authorize writing contract files, code, migrations, or installing dependencies — those remain separate, subsequent Phase 0 tasks.

---

## Future Reconsideration Triggers

This ADR should be revisited, not silently reinterpreted, if any of the following occur:

- An independently-deployed or asynchronously-upgraded consumer appears (a published external API, a shipped Flutter client not deployed in lockstep with the monorepo) — triggers reconsideration of decision 5 (versioning: embedded `contract_version`, possibly a registry).
- The Application API's endpoint/operation surface stabilizes enough that endpoint-level description becomes valuable — triggers reconsideration of decision 1 (adopting OpenAPI on top of the existing JSON Schema layer, not replacing it).
- A second data provider is introduced alongside or instead of API-Football — decision 11's provider-mapping mechanism must be validated against the new provider, not assumed to generalize automatically.
- Any job orchestration logic comes to depend on a specific, closed set of `trigger` or `environment` values — triggers reconsideration of decision 9 (promoting them to closed enums).
- An internal/admin API surface is added that exposes Job Run status to a client — triggers reconsideration of whether `JobStatus`/`JobType` should move from Python-internal to shared (flagged as an open question in the Task 0.3.1 review, not decided by this ADR).
