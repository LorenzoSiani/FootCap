# ADR-010: Run Provenance Phase 0 Semantics

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.4.4E

**Relation to the Architecture Baseline:** This ADR is a Phase 0 implementation/domain decision and does **NOT** modify or reopen `FOOTCAP_ARCHITECTURE_V1.2.1.md`. The Architecture Baseline remains FROZEN. Frozen semantics already owned by `FOOTCAP_ARCHITECTURE_V1.2.1.md`, ADR-009, or the existing shared contract schemas (`packages/contracts/schemas/*.schema.json`) remain authoritative and are not redefined here. Where this ADR touches a topic those sources already settle, it references them rather than restating them.

---

## Context

Architecture Baseline §13 establishes that "the common Job Run links to ingestion_run, feature_run, training_run, prediction_run, or backtest_run," records `job_type, status, started_at, finished_at, trigger, git_commit, git_ref, environment, workflow_run_id, error_summary, metadata`, and that ingestion "uses PENDING, RUNNING, COMPLETED, PARTIAL, FAILED, CANCELLED." `run-provenance.schema.json` implements this, and ADR-009 decisions 9 and 10 already resolved `trigger`/`environment` openness and CI-vs-local git nullability.

A sequence of read-only reviews (Tasks 0.4.4A–0.4.4D) examined the remaining gaps blocking implementation of the Phase 0 Run Engine: whether the common Job Run needs an identity of its own distinct from job-specific run IDs; what `started_at` means for a PENDING record, given `started_at` is required for every status but PENDING is, on its face, a not-yet-started state; how the Run Engine should internally represent execution origin (local/CI/GitHub Actions) and working-tree cleanliness without closing `trigger`/`environment` into taxonomies or adding unnecessary serialized fields; and how conservative the Phase 0 git-provenance rule should be for a dirty or unverified local working tree. Task 0.4.4D reached final, non-reopened decisions on each point. This ADR records those decisions.

No Architecture Baseline invariant, entity, or classification is added, removed, or reinterpreted by this ADR. It resolves *how* Phase 0 fills gaps the baseline left open, the same relationship ADR-009 has to the baseline.

---

## Decision

Adopt the eleven implementation decisions below for Run Provenance Phase 0. `run-provenance.schema.json` is updated only as described in Decision 1 and Decision 2; no other file changes are authorized by this ADR.

### 1. Common Job Run identity: `job_run_id`

Every common Job Run provenance record has an independent `job_run_id`, identifying the common provenance record itself. It is distinct from every job-specific run identifier: `training_run_id`, `prediction_run_id`, `backtest_run_id`, and future `ingestion_run_id`/`feature_run_id`. Shared wire representation is `definitions.schema.json#/$defs/Identifier` — the same opaque, encoding-agnostic string type used by every other identifier in these schemas. No UUID, ULID, or database-specific encoding is mandated. `job_run_id` is required on every `RunProvenance` record.

This is a **NEW CONTRACT SEMANTIC** — Architecture §13's "links to" language implies two ends to that link but never names the linking side's identifier; nothing prior settled this by itself.

### 2. PENDING is a post-start application execution state

A Job Run record only exists once execution has entered FootCap's application execution boundary; `started_at` is recorded at that moment. PENDING is the status a Job Run may hold immediately after crossing that boundary, while waiting for active processing/resources/internal scheduling — not before it. Therefore PENDING always has `started_at`. `started_at` is not external queue-submission time occurring before FootCap's execution boundary, and not a generic record-created-at time.

This is a **NEW CONTRACT SEMANTIC** — the baseline and ADR-009 never defined PENDING's relationship to `started_at`. This decision does not define a RunStatus transition matrix; it defines only the static meaning of one field for one status value.

### 3. `ExecutionOrigin` (internal, Python-only)

The Run Engine represents execution origin internally as a three-value concept: `LOCAL`, `CI`, `GITHUB_ACTIONS`. It is internal domain validation context, mutually exclusive by construction, and supplied authoritatively by the caller — never inferred from `trigger`, `environment`, or `workflow_run_id`. It is not serialized, not persisted as part of `RunProvenance`, and not a shared contract; it does not appear anywhere under `packages/contracts/`.

### 4. `WorkingTreeState` (internal, Python-only)

The Run Engine represents local working-tree cleanliness internally as a four-value concept: `CLEAN` (verified clean), `DIRTY` (verified to contain relevant uncommitted/untracked changes), `UNKNOWN` (applies but was not established), `NOT_APPLICABLE` (does not apply to this execution context). For `LOCAL` origin, `CLEAN`/`DIRTY`/`UNKNOWN` are allowed and `NOT_APPLICABLE` is invalid. For `CI` and `GITHUB_ACTIONS` origin, only `NOT_APPLICABLE` is valid. The Run Engine never inspects Git itself; this value is always caller-supplied by a future CLI/runtime adapter.

### 5. `ExecutionContext` (internal, Python-only)

The minimum internal, immutable context the Run Engine's contextual validation consumes is `ExecutionContext { origin: ExecutionOrigin, working_tree_state: WorkingTreeState }`. No further fields are introduced. It remains separate from `RunProvenance` and is never serialized or persisted.

### 6. Local git provenance policy

For `LOCAL` + `CLEAN`: `git_commit`/`git_ref` may both be present or both be absent; one without the other is invalid. For `LOCAL` + `DIRTY`: `git_commit` and `git_ref` are both absent. For `LOCAL` + `UNKNOWN`: `git_commit` and `git_ref` are both absent.

The DIRTY/UNKNOWN omission rule is a **SAFE CONSERVATIVE PHASE 0 IMPLEMENTATION POLICY**, not a rule ADR-009 already mandates in this exact form — ADR-009 decision 10 establishes that `git_commit`/`git_ref` may be nullable for local runs and that a dirty tree must never be falsely represented as fully reproducible, but does not itself specify omission as the mechanism for the dirty/unknown case. This policy chooses omission because no durable dirty marker exists yet in Phase 0: recording a base commit/ref while the tree is dirty or unverified would risk being read as a full reproducibility claim. The trade-off is explicit — this loses potentially useful base-commit provenance for dirty/unknown local runs, in exchange for never overstating exact reproducibility.

### 7. CI and GitHub Actions git provenance

CI-triggered runs (including GitHub Actions, which is a CI-triggered case) require `git_commit` and `git_ref`. This is not a new decision — it is ADR-009 decision 10, referenced here, not redefined. No commit/ref syntax validation and no Git existence checks are introduced by this ADR or by the Run Engine.

### 8. `workflow_run_id` by origin

`LOCAL`: `workflow_run_id` absent. Generic CI (non-GitHub-Actions): `workflow_run_id` absent. `GITHUB_ACTIONS`: `workflow_run_id` required. The LOCAL/generic-CI absence is directly supported by the existing schema description ("present only when triggered via GitHub Actions"); the GitHub-Actions-required rule is a **Phase 0 completeness policy** enforced by Engine-level contextual/domain validation, not JSON Schema structural validity — `run-provenance.schema.json` does not add `workflow_run_id` to its `required` array. `ExecutionOrigin` is never inferred from `workflow_run_id`'s presence (see Decision 3).

### 9. Phase 0 Run Engine scope: construction and validation only

The Phase 0 Run Engine implements construction and validation only. No `start_run()`, `complete_run()`, `fail_run()`, `cancel_run()`, transition matrix, or lifecycle helper of any kind is implemented. A future dedicated lifecycle decision/ADR, defining valid RunStatus-to-RunStatus transitions and their authorization/atomicity — analogous to Architecture §7.8's frozen `publication_state` transition matrix — is required before any lifecycle helper is introduced.

### 10. Timestamp ordering

When `finished_at` is present, `finished_at >= started_at`; equality is valid. This is a **SAFE IMPLEMENTATION INVARIANT**, not a frozen architectural rule — the baseline never states it explicitly, but it follows directly from the plain meaning of "started" and "finished," and non-strict equality matches the baseline's existing boundary-equality convention (`source_available_at <= prediction_cutoff`, Architecture §5.2). No other timestamp ordering rule is introduced.

### 11. Blank `error_summary` rejected

When `error_summary` is present, blank or whitespace-only text is invalid; it must be rejected, not silently normalized to absent/`None`. This is a **SAFE IMPLEMENTATION QUALITY RULE**, distinct from and additional to the already-frozen status-keyed presence/absence rule for `error_summary` (`run-provenance.schema.json`'s existing description: populated on FAILED/PARTIAL/CANCELLED, absent otherwise), which this ADR does not redefine.

---

## Consequences

- `run-provenance.schema.json` gains a required `job_run_id` field and a clarified `started_at` description; no other schema in `packages/contracts/` changes.
- Every `RunProvenance` value the Run Engine constructs must supply `job_run_id`, closing the identity gap Architecture §13 left implicit.
- PENDING records are no longer ambiguous with respect to `started_at` — every PENDING record has a `started_at` at FootCap's application execution boundary, and no code path may treat PENDING as pre-start.
- The Run Engine's contextual validation depends on two new internal-only types (`ExecutionOrigin`, `WorkingTreeState`) supplied by the caller; no future CLI/runtime adapter exists yet to populate them from real Git/CI state, so this ADR does not itself unblock end-to-end operation — only construction/validation of caller-supplied facts.
- Dirty/unknown local runs lose base-commit provenance in Phase 0 (Decision 6); this is a deliberately revisitable trade-off, not a permanent architectural position.
- No RunStatus transition helper may be implemented until a separate lifecycle ADR exists (Decision 9); this ADR is not that document.

---

## Rejected Alternatives

1. **Using a job-specific run ID (e.g. `training_run_id`) as the identity of the common Job Run** — rejected because job-specific IDs are polymorphic across job types and a Job Run may exist, run, or fail before any job-specific run record exists; conflating the two would leave common provenance without stable identity in exactly the cases it matters most.
2. **Omitting `job_run_id` entirely** — rejected because the common Job Run is the authoritative execution record (Architecture §19) and needs subtype-independent correlation; without its own identity it cannot be referenced except through a job-specific record that may not yet exist.
3. **Treating PENDING as pre-start external queue state while keeping `started_at` required** — rejected because it directly contradicts the schema's own `started_at` requirement for every status; a pre-start PENDING record would either need a fabricated `started_at` or a schema change, neither acceptable.
4. **Redefining `started_at` as generic record-created-at time** — rejected because it discards the field's documented meaning ("execution started") for every status, not just PENDING, weakening the field everywhere to resolve an ambiguity that only existed for one status value.
5. **Boolean pair `is_ci` + `is_github_actions`** — rejected because it permits an invalid combination (`is_github_actions=True, is_ci=False`) that must be rejected by a runtime check rather than being unrepresentable; a three-value `ExecutionOrigin` makes the invalid state unconstructible.
6. **`working_tree_dirty: bool | None` with ambiguous `None` semantics** — rejected because `None` was forced to mean two different things ("not applicable" for CI and "unknown" for an unchecked local tree) with no way to distinguish them; `WorkingTreeState`'s four explicit values remove the ambiguity.
7. **Inferring execution origin from `trigger`/`environment`/`workflow_run_id`** — rejected because `trigger` and `environment` are deliberately open, free-form strings (ADR-009 decision 9); parsing them to infer origin would build a hidden closed taxonomy over fields the project has explicitly chosen to keep open.
8. **Recording `git_commit`/`git_ref` for DIRTY/UNKNOWN local runs without a durable dirty marker** — rejected because, absent a marker distinguishing "exact reproducible commit" from "base commit of a dirty/unverified tree," a consumer could not tell the two apart and would risk treating a dirty run as fully reproducible, which ADR-009 decision 10 already prohibits in substance.
9. **Adding lifecycle transition helpers in Phase 0** — rejected because no RunStatus transition matrix has been designed or frozen; adding helpers now would encode transition rules nobody has actually decided, the same risk `publication_state` avoided by freezing its matrix before any lifecycle operation was implemented.
10. **Encoding all contextual/domain rules directly into JSON Schema** — rejected because `packages/contracts/README.md` already establishes that JSON Schema in this project validates structural shape only; cross-field and contextual rules (status-keyed coupling, origin-keyed git rules, timestamp ordering) are Engine/domain logic by design, and encoding them as schema `if/then/else` would duplicate that logic in a second, driftable location.

---

## Scope

This ADR governs only the Run Provenance Phase 0 decisions listed above. It does not:

- redefine the status ↔ `finished_at` presence/absence table already frozen in `run-provenance.schema.json`'s field descriptions;
- redefine the status ↔ `error_summary` presence/absence table already frozen in `run-provenance.schema.json`'s field descriptions;
- redefine or restate ADR-009's CI git-required rule (decision 10) beyond referencing it;
- change any invariant, entity, classification, or lifecycle rule defined in `FOOTCAP_ARCHITECTURE_V1.2.1.md`;
- define a RunStatus transition matrix;
- implement the Run Engine, any Python code, tests, persistence, serialization, Git inspection, environment inspection, or a CLI/runtime adapter — those remain separate, subsequent tasks.

---

## Future Reconsideration Triggers

This ADR should be revisited, not silently reinterpreted, if any of the following occur:

- A durable dirty-working-tree marker is introduced — triggers reconsideration of Decision 6's omission-only policy for DIRTY/UNKNOWN local runs (a base-commit-plus-marker representation could then preserve more provenance without overstating reproducibility).
- A CLI or other runtime adapter is implemented that actually performs Git inspection — triggers definition of exactly how it populates `ExecutionOrigin` and `WorkingTreeState`, which this ADR deliberately leaves to that future adapter.
- Lifecycle transition design begins — triggers a separate, dedicated ADR for the RunStatus transition matrix (Decision 9); this ADR must not be silently extended to cover it.
- Persistence is implemented for `RunProvenance` — may surface storage-level questions (e.g. concrete `job_run_id` encoding at the database layer) that this ADR intentionally leaves open, consistent with `Identifier`'s own encoding-agnostic definition.
- A CI provider other than GitHub Actions needs richer provenance than "generic CI" currently captures — triggers reconsideration of Decision 8's flat generic-CI/`workflow_run_id`-absent rule.
- A serialization layer is implemented for `RunProvenance` — triggers verification that `None`-valued optional fields are dropped from the wire payload rather than emitted as JSON `null`. For `RunProvenance` specifically: Python `None` on an optional field represents omission at the wire boundary, not JSON `null`. The optional `RunProvenance` fields — `finished_at`, `git_commit`, `git_ref`, `workflow_run_id`, `error_summary` — must be omitted from serialized JSON when absent, never emitted as `null`, because `run-provenance.schema.json` does not permit JSON `null` for those fields.
