# ADR-014: Season Identity and Bootstrap Semantics

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.5.7B

**Relation to the Architecture Baseline:** This ADR is a Phase 0 implementation/domain decision and does **NOT** modify or reopen `FOOTCAP_ARCHITECTURE_V1.2.1.md`. The Architecture Baseline remains FROZEN. ADR-011 remains authoritative for the provider identity/raw observation boundary. ADR-012 remains authoritative for `ProviderEntityRef` and provider identity resolution. ADR-013 remains authoritative for entity creation/bootstrap semantics generally, outside the Season-specific refinements this ADR records. This ADR does not redefine any of them — it resolves the one boundary ADR-013 explicitly left open: Season identity and Season-specific bootstrap authorization.

---

## Context

ADR-011 decision 3 already established that API-Football season is contextual request/domain data represented by a four-digit starting year, is not a `ProviderEntityRef`, and that FootCap Season persistence identity remains deferred. ADR-013 decision 12 confirmed Season semantics block Match bootstrap/fixture normalization but do not block Competition/Team bootstrap, and explicitly declined to decide whether `(competition_id, start_year)` is a natural key, a value object, sufficient identity, or opaque-ID input.

Task 0.5.7A produced a read-only Season design review; Task 0.5.7A.1 adversarially reviewed it and approved it with changes — most significantly, correcting an initial conclusion that a curated Competition alone was sufficient authority to auto-create any Season a provider happened to report. This ADR records the corrected, final decision cluster so that Season identity and bootstrap authorization are settled before Competition/Team/Season implementation proceeds.

This ADR does not design: a concrete opaque `season_id` generator; persistence schema, tables, columns, or migrations; repository interfaces; transaction/locking/concurrency mechanics; a generic provider-season mapping abstraction; correction/reconciliation workflow; or Match/participation persistence shape.

---

## Decision

Adopt the twenty-five decisions below as Season Identity and Bootstrap Semantics for Phase 0. No code, tests, migrations, or dependencies are introduced by this ADR — it records decisions to be executed in a subsequent Phase 0 implementation task.

### 1. Phase 0 Season model

Season is a Competition-scoped immutable value object for Phase 0, not currently a first-class entity with an opaque generated identifier. Conceptual minimum shape (semantic shape only, not a frozen Python implementation):

```
Season(
    competition_id: str,
    start_year: int,
)
```

### 2. Natural identity

For Phase 0, Season semantic identity is `(competition_id, start_year)`. Both components are identity. Two Seasons with different `competition_id` values are distinct even if `start_year` is equal. Two Season values with the same exact `competition_id` and `start_year` represent the same FootCap Season.

This is scoped explicitly to the current Phase 0/V1 model. It is not claimed to be universally sufficient for every football competition format forever (see decision 23 and Future Reconsideration Triggers).

### 3. `season_id`

No opaque `season_id` is introduced in Phase 0. This is an explicit deferral, not a permanent prohibition — future persistence, participation, provider, or relationship requirements may justify adding an opaque surrogate identifier later. Adding such an ID later does not inherently change Season semantic identity, provided the natural identity (decision 2) remains stable.

### 4. Semantic uniqueness

Within the Phase 0 Season model, at most one FootCap Season exists for an exact `(competition_id, start_year)` pair. This is a semantic invariant only — it does not prescribe `UNIQUE(competition_id, start_year)` or any other SQL/physical persistence syntax. Physical enforcement belongs to persistence design (decision 24).

### 5. Competition scope

A Season belongs to exactly one FootCap Competition. `competition_id` is intrinsic to Season identity; a bare `start_year` is insufficient Season identity on its own. No Competition metadata beyond `competition_id` itself is introduced into Season identity.

### 6. `start_year` and provider normalization

`start_year` is part of Season identity, not mutable metadata. For API-Football, the provider season integer is normalized directly to FootCap `start_year`. The provider convention recorded here is narrow: API-Football represents a season with a four-digit starting-year value, and cross-year seasons use their starting year. This rule is not generalized to every future provider (see decision 17).

### 7. Temporal representation

Phase 0 Season stores only `start_year`. `end_year`, `start_date`, and `end_date` are not required. These may become domain metadata later if a concrete consumer requires them; they are not derived or fabricated now.

### 8. Label

Season label is presentation/domain-display metadata, not identity. No label field is part of the minimum Phase 0 Season value. Examples such as `2025/26`, `2025`, or `2026` must not themselves define Season identity. Formatting belongs to a future API/UI/display concern unless a concrete identity collision demonstrates otherwise.

### 9. `ProviderEntityRef` exclusion

Season remains outside `ProviderEntityRef`. This does not reopen ADR-011 or ADR-012. For API-Football, the season value is provider request/domain context, not a standalone provider-assigned entity identifier. `ProviderEntityRef(entity_type="season")` is not introduced into the supported identity correspondence.

### 10. `ProviderIdentityMapping` exclusion

Season does not use `ProviderIdentityMapping` in Phase 0. No Season mapping is introduced through the existing identity resolver. API-Football Season resolution is based on a resolved FootCap `competition_id` plus a normalized provider season year — not a provider Season entity reference.

### 11. Resolution order

Competition must resolve before Season. Conceptual flow: provider league identity → FootCap `competition_id` → normalized provider season year → FootCap `Season(competition_id, start_year)`. There is no direct provider-season resolution independent of Competition.

### 12. Resolution semantics

The conceptual Season lookup resolves by `(competition_id, start_year)` and returns the corresponding Season value. No exact repository/API method signature is frozen by this ADR. A future implementation may expose something analogous to `resolve_season(...)`, but exact method naming and repository abstraction are implementation details.

### 13. Creation authorization

A curated/authorized Competition alone is **not** sufficient authority to create any Season value a provider happens to report. A missing Season may be created only when its exact Competition **and** provider-season context has been explicitly authorized as an ingestion/bootstrap target. This prevents an incidental provider response, or a structurally valid but otherwise unexpected season value, from silently expanding FootCap domain state. Four-digit range validation (already enforced at the provider-DTO layer) is necessary provider validation, but it is not creation authorization. The physical configuration mechanism for expressing "this exact Competition/provider-season context is authorized" is not defined here.

### 14. Uniform current/historical policy

There is no separate semantic policy for a current Season versus a historical Season. Both current and historical Seasons may be created when their exact Competition/provider-season context is explicitly authorized for ingestion/bootstrap (decision 13). No special "current Season must be curated manually" rule is frozen.

### 15. Creation idempotency

Repeated processing of the same authorized `(competition_id, start_year)` must reuse the existing Season. It must not create a duplicate semantic Season. Concurrency and physical uniqueness enforcement remain deferred to persistence design (decision 24).

### 16. Provider independence

Season semantic identity does not contain: provider name, the provider's raw season value as a separate identity field, `RawObservation`, or `job_run_id`. API-Football's season integer becomes `start_year` after provider-specific normalization; no duplicate provider-specific identity field is preserved inside Season.

### 17. Future providers

It is not assumed that every provider can be reduced losslessly to `start_year`. The Phase 0 design is accepted for API-Football/V1. A future provider may expose opaque season IDs, ending-year identifiers, labels, edition identifiers, tournament cycles, or other context that cannot be normalized losslessly to the Phase 0 Season model — if so, Season design must be reconsidered (see Future Reconsideration Triggers). No generic provider-season mapping abstraction is introduced now.

### 18. Correction semantics

Because `start_year` is identity (decision 6), changing `start_year` means changing Season identity — it is not an ordinary metadata update. A provider correction that demonstrates the original `start_year` was wrong requires identity reconciliation. Reconciliation mechanics are not designed in this ADR; an operationally significant start-year correction is recorded as a Future Reconsideration Trigger instead.

### 19. Match implication

The Phase 0 Season model is sufficient for Match normalization to carry Season semantics through `competition_id` + `season_start_year`, or an equivalent embedded Season value. No `season_id` is required merely for Match normalization. Match persistence schema is not frozen here.

### 20. Team participation implication

A future participation relationship can semantically reference Season through `competition_id` + `season_start_year`, without requiring `season_id`. Whether persistence later benefits from a surrogate Season foreign key remains deferred.

### 21. Backtesting

For the initial Serie A scope, Competition + `start_year` is sufficient for Season grouping in historical ingestion/backtesting. Season dates or a `season_id` are not made requirements of Dixon-Coles or rolling-origin evaluation. Actual chronology remains governed by Match timestamps and the already-frozen temporal semantics (Architecture §5; ADR-002/ADR-008 as referenced there).

### 22. Temporal Engine boundary

Season is not automatically a `MaterialFact`. Season is not assigned `event_at`, `source_available_at`, `prediction_cutoff`, or `temporal_classification` merely because it exists as a domain value. Temporal evidence remains attached to the actual provider observations and normalized facts already governed by the existing architecture/contracts.

### 23. Collision policy

The natural identity (decision 2) is intentionally scoped to Phase 0/V1. Competition identity must not be distorted merely to preserve the Season key. If FootCap encounters two genuinely distinct Seasons belonging to the same Competition and sharing the same `start_year`, that is a trigger to reconsider Season identity (see Future Reconsideration Triggers) — no additional discriminator is invented now.

### 24. Persistence boundary

This ADR does not define tables, columns, foreign keys, indexes, SQL uniqueness constraints, repository protocols, transactions, locking, or concurrency mechanics. Persistence design must preserve: semantic Season uniqueness (decision 4); creation idempotency (decision 15); creation authorization (decision 13); and Competition scoping (decision 5). The physical mechanism for preserving these remains open.

### 25. Next implementation sequence

The accepted sequencing consequence: ADR-014 → minimal Season value implementation → persistence design → Competition/Team/Season bootstrap implementation. This is sequencing guidance, not a persistence design. The minimal Season value (decision 1) is stable enough to implement before storage exists, while bootstrap atomicity/storage/authorization should be designed against the persistence boundary (decision 24) rather than expanded substantially in-memory first.

---

## Consequences

- Season identity is settled well enough for Competition/Team/Season implementation to proceed without inventing semantics ad hoc, while genuinely open questions (opaque ID, cross-provider fit, correction workflow) remain explicitly deferred rather than silently decided.
- The corrected creation-authorization rule (decision 13) closes the gap the adversarial review identified: an authorized Competition no longer implicitly authorizes creation of every Season value any provider response happens to mention, preventing incidental or malformed provider data from silently expanding FootCap's domain state.
- A single uniform creation policy (decision 14) means historical backtesting ingestion (`docs/product/FOOTCAP_MASTER_BRIEF.md` §11's "approximately three Serie A seasons") and current-season ingestion share one authorization rule, with no separate manual-curation carve-out to maintain.
- Match and future participation modeling can proceed using `competition_id` + `start_year` without waiting on an opaque `season_id` decision (decisions 19-20).
- Provider independence is preserved (decision 16): Season identity contains nothing API-Football-specific beyond a value already normalized into FootCap's own `start_year` field, consistent with ADR-012's provider-independence guarantee for other entities.

---

## Rejected Alternatives

1. **Opaque `season_id` required immediately** — rejected; no current consumer requires it, and minting one now would be identity ahead of need (decision 3).
2. **Season identified by `start_year` alone** — rejected; the same `start_year` legitimately identifies different Seasons under different Competitions (decision 5).
3. **Season as `ProviderEntityRef`** — rejected; API-Football's season value is request/domain context, not a standalone provider-assigned entity identifier (decision 9).
4. **Reuse `ProviderIdentityMapping` for Season** — rejected; there is no provider Season entity reference for such a mapping to bridge (decision 10).
5. **Dedicated generic provider-season mapping abstraction now** — rejected; no second provider exists yet to justify generalizing beyond direct `start_year` normalization (decision 17).
6. **Store `end_year` by deriving `start_year + 1`** — rejected; this is not reliably correct for calendar-year competitions and would require competition-format knowledge Season does not track (decision 7).
7. **Require `start_date`/`end_date` immediately** — rejected; API-Football exposes season-level start and end dates, but no current FootCap consumer requires them in the minimum core Season value. Their validation, persistence, correction semantics, and domain use remain deferred until a concrete consumer requires them (decision 7).
8. **Store label as identity** — rejected; label format depends on competition shape and must never gate identity equality (decision 8).
9. **Treat authorized Competition alone as Season creation authority** — rejected; this was the adversarial-review correction itself — Competition authorization alone would let any provider-reported season value silently create domain state (decision 13).
10. **Separate current-vs-historical creation policy** — rejected; one uniform authorized-context rule is simpler and equally safe (decision 14).
11. **Automatically create every structurally valid provider Season** — rejected; structural validity (a four-digit year) is not creation authorization (decision 13).
12. **Include provider in Season identity** — rejected; would reintroduce a provider dependency into FootCap identity, contradicting ADR-012's provider-independence goal (decision 16).
13. **Include `RawObservation`/`job_run_id` in Season identity** — rejected; conflates durable domain identity with point-in-time execution/observation provenance, the same distinction ADR-011/ADR-010/ADR-013 already draw for other entities (decision 16).
14. **Freeze SQL `UNIQUE` syntax now** — rejected; physical enforcement belongs to persistence design, not this semantic ADR (decision 4, decision 24).
15. **Add a speculative collision discriminator now** — rejected; no genuine collision case has been observed; inventing one preemptively would be unjustified complexity (decision 23).
16. **Force Competition identities to split merely to preserve the Season key** — rejected; Competition identity is governed by ADR-013, not distorted to rescue an assumption in Season's natural key (decision 23).
17. **Make Season automatically a `MaterialFact`** — rejected; Season is domain context, not a temporally-evaluated fact (decision 22).

This ADR does not reject a future opaque `season_id` or a future provider-season correspondence mechanism as permanently invalid — both are deferred, not forbidden (decision 3, decision 17).

---

## Scope / Deferrals

This ADR governs only the twenty-five decisions above. It explicitly defers, without deciding:

- opaque `season_id`;
- persistence schema;
- table/column names;
- physical uniqueness enforcement;
- foreign-key design;
- repository protocols;
- transaction/locking mechanics;
- concurrent creation behavior;
- provider-season correspondence for future providers;
- an additional Season identity discriminator;
- `end_year`;
- `start_date`;
- `end_date`;
- stored/display label;
- Competition-format classification;
- UI Season representation;
- Team participation persistence;
- correction/reconciliation workflow;
- multi-provider Season reconciliation;
- Match persistence shape;
- bootstrap configuration/storage mechanism;
- exact Season resolver/repository API;
- historical/current target configuration.

It does not change any invariant, entity, classification, or lifecycle rule defined in `FOOTCAP_ARCHITECTURE_V1.2.1.md`, and it does not redefine anything already frozen by ADR-009, ADR-010, ADR-011, ADR-012, or ADR-013.

---

## Future Reconsideration Triggers

This ADR should be revisited, not silently reinterpreted, if any of the following occur:

1. A real same-Competition/same-`start_year` Season collision is found.
2. A second provider cannot normalize Season context losslessly to `start_year`.
3. A provider exposes a genuine standalone Season identifier.
4. Competition formats require an additional discriminator beyond `(competition_id, start_year)`.
5. Start-year corrections become operationally significant.
6. Persistence materially benefits from an opaque Season identity.
7. Participation requires a stable Season foreign key.
8. Multi-provider Season reconciliation becomes necessary.
9. A concrete consumer requires `end_year`/`start_date`/`end_date`.
10. API/UI requirements demonstrate that label carries semantic rather than merely presentation meaning.
11. Creation-authorization requirements become richer than exact Competition/provider-season target authorization.

No resulting solution for any of these triggers is pre-decided by this ADR.
