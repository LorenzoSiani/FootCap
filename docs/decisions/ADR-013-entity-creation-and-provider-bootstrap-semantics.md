# ADR-013: Entity Creation and Provider Bootstrap Semantics

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.5.6B

**Relation to the Architecture Baseline:** This ADR is a Phase 0 implementation/domain decision and does **NOT** modify or reopen `FOOTCAP_ARCHITECTURE_V1.2.1.md`. The Architecture Baseline remains FROZEN. ADR-011 remains authoritative for the provider identity/raw observation boundary; ADR-012 remains authoritative for provider-to-FootCap identity correspondence and resolution. This ADR does not redefine either. It defines what happens next: what FootCap is authorized to do when a provider entity falls within FootCap's authorized bootstrap scope but no FootCap entity or `ProviderIdentityMapping` exists for it yet.

---

## Context

Task 0.5.6A produced a read-only design review of the entity-creation/provider-bootstrap boundary, concluding **READY WITH ADR**. `IdentityResolver` (ADR-012; Task 0.5.5D) is strict and resolution-only by design — it deliberately never creates entities, generates FootCap IDs, or creates missing mappings. Something must now decide what happens on a genuine miss: when a provider reference is structurally valid, has a supported provider/entity_type correspondence (ADR-012 decision 3), but has never been mapped before.

That decision is not uniform across FootCap's domain entities — Competition, Team, and Match carry materially different creation risk, and Season remains an open concept this ADR does not resolve. This ADR records the resulting Phase 0 decision cluster so that a subsequent implementation task can build entity creation and bootstrap logic against settled semantics rather than ad hoc judgment calls.

It does **not** design: a concrete FootCap ID generator; Season identity; exact domain-entity field lists; persistence schema or migrations; repository interfaces; transaction implementation; concurrency control; alias reconciliation/merge workflow; metadata refresh policy; a participation/membership model; normalized Match implementation; or orchestration.

---

## Decision

Adopt the nineteen decisions below as Entity Creation and Provider Bootstrap Semantics for Phase 0. No code, tests, migrations, or dependencies are introduced by this ADR — it records decisions to be executed in a subsequent Phase 0 implementation task.

### 1. Creation policy is entity-type-specific

FootCap does not use one universal "unresolved provider identity → auto-create entity" rule. Creation policy depends on the domain entity type:

- **Competition:** CURATED / EXPLICIT.
- **Team:** CONDITIONALLY AUTO-CREATABLE.
- **Match:** DEPENDENT CONSTRUCTION AFTER COMPLETE RESOLUTION.
- **Season:** NOT DECIDED BY THIS ADR (decision 12).

A universal auto-create rule is wrong because it would let an incidental provider response (e.g. an unrelated competition's metadata surfacing during an API call) silently expand FootCap's domain state without a product decision behind it. A universal block rule is wrong because it would make ordinary, low-risk discovery (a team appearing under a competition FootCap has already explicitly decided to track) require manual intervention for every single record, defeating the purpose of a bootstrap mechanism. The correct policy differentiates by the actual risk profile of each entity type.

### 2. Competition is curated

A provider League response does not by itself authorize creation of a FootCap Competition. API-Football provides provider facts; FootCap decides whether a Competition belongs in its product/catalog scope. For V1, Serie A is explicitly curated as the initial tracked Competition.

No concrete API-Football league ID is frozen by this ADR, and Serie A is not hard-coded into any generic domain type. The concrete seed representation (how "FootCap tracks Serie A" is actually expressed in code or data) remains deferred to implementation.

### 3. Team conditional auto-creation

A Team may be automatically created only when discovered through an already-authorized Competition bootstrap context — conceptually, discovery driven by a curated Competition plus a provider season parameter. This context authorizes discovery; it does not become part of Team identity (decision 4).

An arbitrary unresolved provider Team reference observed outside an authorized bootstrap context must not automatically create a Team. This ADR does not define transport/API-call mechanics; "authorized bootstrap context" is a semantic condition, not a specific endpoint contract.

### 4. Team identity is competition- and season-independent

A FootCap Team is not identified by competition, season, competition + season, or competition membership. A Team that appears across multiple seasons remains the same FootCap Team as long as its provider correspondence remains the same. Competition/season participation is contextual domain state, not Team identity. A future participation/membership relation may exist but is not designed here.

### 5. No name-based identity inference

When a provider Team reference is unresolved, FootCap must not automatically infer an existing FootCap Team by exact name, fuzzy name, normalized name, code, country + name, or any other metadata heuristic. Provider metadata may inform future manual reconciliation, but never establishes identity automatically.

ADR-012 already allows multiple provider references to map to one FootCap entity (decision 8 of that ADR) through the explicit `ProviderIdentityMapping` mechanism. Automatic name matching would bypass that explicit mechanism with an implicit, error-prone one — two clubs sharing a similar or identical name, or one club renaming itself, would silently corrupt identity in either direction.

### 6. Alias / duplicate risk

Conditional Team auto-creation (decision 3) can still create a duplicate FootCap Team if a new, unresolved provider ID is actually an alias for an already-existing real-world Team and no mapping exists yet connecting the two. Phase 0 accepts this as a bounded risk under the small, curated V1 scope (decision 15) — a single curated competition's team list is small enough to be manually reviewable. No automatic merge logic is invented here, and no reconciliation workflow is frozen. Manual/reconciliation/merge semantics remain deferred.

### 7. Entity creation and first mapping are one logical operation

Conceptually, entity creation is three steps: create the FootCap entity, obtain its FootCap entity ID, create the `ProviderIdentityMapping`. These three steps must behave as one logical atomic operation.

Durable invariant: a successful bootstrap creation must never expose a newly-created entity without its first provider mapping. Reason: if entity creation succeeds but mapping creation fails, the next bootstrap rerun — still unable to resolve the same provider reference — would create a second entity for what is really the same provider record, a self-inflicted instance of the decision 6 duplicate risk. No SQL transaction syntax or repository API is chosen here; only the semantic atomicity requirement is recorded.

### 8. Bootstrap idempotency

Rerun semantics:

- If a provider reference already resolves, reuse the existing FootCap entity ID; create nothing.
- If unresolved and creation is authorized (per decisions 1-3), create the entity and its first mapping exactly once, as the single logical operation from decision 7.
- If unresolved and creation is not authorized, create nothing and report/block the unresolved identity.

Bootstrap must be safely rerunnable under these rules. Concurrency mechanics (e.g. two simultaneous bootstrap runs racing on the same unresolved reference) are not solved here.

### 9. FootCap ID must remain provider-independent

Deterministic FootCap IDs derived from provider identity are explicitly rejected. This includes, without limitation: `hash("api-football/team/505")`, `"api-football-team-505"`, reusing the provider ID directly, or any provider-prefixed provider ID. `ProviderIdentityMapping` (ADR-012) remains the sole bridge between provider and FootCap identity; FootCap entity ID encoding itself remains opaque and independent of any provider's identifier scheme.

### 10. ID generation mechanism not frozen

This ADR does not choose UUID vs. ULID vs. another opaque generator. It records only:

- FootCap IDs must satisfy the existing `Identifier` semantics (`definitions.schema.json`) — opaque, no specific encoding assumed;
- generation must not depend on provider identity (decision 9);
- the concrete generation mechanism is an implementation detail;
- tests may inject or caller-supply deterministic opaque IDs, exactly as `engine/tests/domain/test_identity.py` already does for `ProviderIdentityMapping.footcap_entity_id`.

Database-generated IDs are not mandated by this ADR.

### 11. Match creation timing

A provider Fixture must not create a FootCap Match merely because its fixture mapping is unresolved. Match construction requires successful resolution of all required FootCap references first — at minimum: Competition, Season, Home Team, and Away Team. Only after those references exist may a new FootCap Match identity be created and the Fixture→Match `ProviderIdentityMapping` established. No placeholder IDs and no partially-resolved Match entities are permitted at any point.

A future normalization implementation may combine these steps into one operation; this ADR freezes only the dependency ordering, not the implementation shape.

### 12. Season remains open

Season identity is not defined by this ADR. This ADR explicitly does not decide whether `(competition_id, start_year)` is a natural key, a value object, sufficient identity on its own, input to a separately-generated opaque `season_id`, or something else. Season design is required before Match bootstrap/normalization can be implemented in full (decision 11 depends on Season resolution). Season does not block Competition/Team bootstrap (decision 15).

### 13. API-Football authority boundary

API-Football is authoritative for its own provider IDs and provider-observed facts. FootCap is authoritative for FootCap entity identity, catalog/product scope, alias reconciliation, entity lifecycle, and whether a given provider entity becomes FootCap domain state at all. A provider response is evidence/data; it is never, by itself, automatic domain-creation authority.

### 14. Provider metadata is not domain identity

Fields such as `name`, `code`, `country`, `founded`, `national`, `logo`, and league `type` may be useful provider facts or initial entity metadata. They must never become hidden identity keys. Changing metadata (e.g. a team renaming itself) must never silently change FootCap identity. Metadata refresh/update policy remains deferred.

### 15. Bootstrap scope for Phase 0

The initial bootstrap target is intentionally narrow. V1 begins with a curated Serie A Competition. Phase 0 bootstrap should first establish Competition + Teams + their `ProviderIdentityMapping`s. Match bootstrap is not required in the same implementation slice. Season may be designed immediately before or after that Team/Competition work. Serie A specificity belongs in curated seed data, not hard-coded into generic domain primitives (`ProviderEntityRef`, `ProviderIdentityMapping`, `IdentityResolver` remain entity- and competition-agnostic, unchanged by this ADR).

### 16. Persistence is not defined here

This ADR records semantics, not physical storage. It does not define tables, columns, foreign keys, migration syntax, Supabase APIs, repository classes, or transaction implementation. It records only that future persistence must preserve: entity + first mapping atomicity (decision 7); `ProviderIdentityMapping` forward uniqueness from ADR-012; and bootstrap idempotency (decision 8). Mapping persistence should be designed alongside domain entity persistence, not as an unrelated afterthought.

### 17. Raw observation durability is not a creation precondition

Entity bootstrap does not require `RawObservation`/`RawContent` to have been durably persisted before entity creation. ADR-011 remains authoritative for raw provenance semantics. Fetch, capture, parse, and bootstrap may all occur within one execution; physical raw-storage ordering remains deferred.

### 18. No new job type

This ADR does not add `IDENTITY_BOOTSTRAP`, `DOMAIN_BOOTSTRAP`, or any other `JobType`. Architecture §13's job types, and `engine/src/footcap_engine/runs/provenance.py`'s current `JobType` Literal (`ingestion`, `features`, `training`, `prediction`, `backtest`), remain authoritative. For now, bootstrap is part of the ingestion/domain-processing flow. This should be reconsidered only if future orchestration demonstrates that bootstrap genuinely requires an independently observable lifecycle distinct from ordinary ingestion.

### 19. Entity mutability boundary

FootCap entity identity is stable after creation. Non-identity metadata may evolve without creating a new entity identity. This ADR does not design event sourcing, entity history, metadata refresh scheduling, source correction history, or merge history, and does not over-specify Python dataclass mutability mechanics beyond this semantic rule.

---

## Consequences

- Bootstrap implementation has a settled, entity-type-differentiated creation policy to build against, rather than needing to invent one ad hoc per entity type.
- Competition catalog growth remains a deliberate FootCap decision, not an incidental side effect of any API-Football call that happens to include league metadata.
- Team discovery can proceed automatically within a curated competition's scope without each individual team requiring manual approval, while still bounding the blast radius of that automation.
- The known duplicate-entity risk from unresolved aliases (decision 6) is accepted, not hidden — a future reconciliation task has an explicit, acknowledged problem to solve rather than a silently-corrupted dataset to first discover.
- FootCap identity remains fully provider-independent (decisions 9-10), preserving ADR-012's alias-safe mapping design and leaving room for a second provider without an identity-scheme rewrite.
- Season and Match remain correctly sequenced as open work rather than being prematurely and incompletely decided as a side effect of Team/Competition bootstrap.

---

## Rejected Alternatives

1. **Auto-create every unresolved provider entity** — rejected; treats Competition, Team, and Match as equally low-risk when they are not (decision 1).
2. **Require manual creation for every entity type** — rejected; would make even low-risk, in-scope Team discovery require manual intervention per record, defeating the purpose of bootstrap.
3. **Auto-create Competition from every API-Football League** — rejected; API-Football's `league` endpoint conflates domestic leagues, cups, tournaments, and international competitions, and would let an incidental call silently expand FootCap's catalog without a product decision (decision 2).
4. **Treat Team identity as competition-bound** — rejected; a Team's real-world identity does not depend on which competition FootCap happens to have discovered it through (decision 4).
5. **Treat Team identity as season-bound** — rejected; the same team persists across seasons under the same provider correspondence (decision 4).
6. **Infer Team identity automatically from exact name** — rejected; distinct clubs can share a name, and this would bypass the explicit `ProviderIdentityMapping` mechanism ADR-012 already establishes (decision 5).
7. **Infer Team identity automatically from fuzzy/normalized name** — rejected for the same reason as exact-name matching, with a strictly higher false-positive risk (decision 5).
8. **Derive FootCap IDs deterministically from provider IDs** — rejected; would reintroduce a provider-identity dependency into FootCap identity encoding, undermining ADR-012's provider-independence guarantee (decision 9).
9. **Reuse provider IDs as FootCap IDs** — rejected; already contradicted by ADR-011 decision 2 and ADR-012 decision 1; restated here as it applies directly to entity creation (decision 9).
10. **Create entity first and persist mapping later without atomicity** — rejected; a partial failure between the two steps creates exactly the duplicate-entity risk decision 7 exists to prevent.
11. **Create Match before all required domain references resolve** — rejected; would produce a Match with an incomplete or fabricated identity, contradicting ADR-011 decision 4's already-frozen unresolved-identity boundary (decision 11).
12. **Use placeholder IDs for unresolved Match references** — rejected for the same reason as alternative 11; a placeholder is functionally a fabricated identity.
13. **Define Season identity opportunistically inside Match creation** — rejected; Season is a genuinely open design question deserving its own review, not an incidental decision made as a side effect of implementing Match creation (decision 12).
14. **Require raw-observation persistence before any bootstrap work** — rejected; conflates semantic correctness with physical durability, which ADR-011 already treats as separable concerns (decision 17).
15. **Introduce a dedicated bootstrap JobType now** — rejected; no current orchestration need distinguishes bootstrap from ordinary ingestion, and Architecture §13's job types are not casually extended (decision 18).

This ADR does not reject UUID, ULID, specific repository protocols, or specific database transaction APIs — these remain intentionally open implementation choices (decision 10, decision 16).

---

## Scope / Deferrals

This ADR governs only the nineteen decisions above. It explicitly defers, without deciding:

- concrete FootCap ID generator;
- Season identity semantics;
- Team/Competition/Match Python model exact field lists;
- persistence schema;
- Supabase migrations;
- repository interfaces;
- transaction implementation;
- concurrency control;
- alias reconciliation;
- merge workflow;
- metadata refresh policy;
- source correction/version history;
- participation/membership model;
- normalized Match implementation;
- Match persistence;
- raw-storage implementation;
- orchestration;
- new JobType;
- admin/catalog-management UI;
- multi-provider reconciliation.

It does not change any invariant, entity, classification, or lifecycle rule defined in `FOOTCAP_ARCHITECTURE_V1.2.1.md`, and it does not redefine anything already frozen by ADR-009, ADR-010, ADR-011, or ADR-012.

---

## Future Reconsideration Triggers

This ADR should be revisited, not silently reinterpreted, if any of the following occur:

- A second data provider is added.
- Provider ID churn/alias duplication becomes operationally meaningful (i.e. decision 6's accepted risk stops being bounded).
- Multi-competition catalog expansion begins, testing whether the curated-Competition model (decision 2) still fits.
- Persistence schema implementation begins.
- Season design begins.
- Match normalization begins.
- Automated reconciliation becomes necessary.
- Team participation/membership becomes a product requirement.
- Bootstrap becomes an independently orchestrated operational job, reopening decision 18.

No resulting solution for any of these triggers is pre-decided by this ADR.
