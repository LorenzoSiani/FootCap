# ADR-015: Core Domain Persistence Semantics

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.5.8B

**Relation to the Architecture Baseline:** This ADR is a subordinate Phase 0 persistence decision. It does **not** modify or reopen `FOOTCAP_ARCHITECTURE_V1.2.1.md`. Supabase/PostgreSQL is already the frozen authoritative durable store; this ADR does not introduce that technology choice. ADR-011 remains authoritative for provider identity and raw-observation semantics, ADR-012 for provider identity mapping and resolution, ADR-013 for entity creation/bootstrap semantics, and ADR-014 for Season identity and authorization. This ADR defines only the minimum durable representation and transaction semantics for the first normalized core-domain persistence slice.

---

## Context

FootCap now has settled semantics for provider-independent identity, provider-to-FootCap mappings, bootstrap creation, and Competition-scoped Season identity. Those semantics cannot survive process restarts if Seasons and mappings exist only as in-memory values. The first persistence slice must therefore make Competition, Team, Season, and provider identity correspondence durable while preserving the exact cardinality, authorization, and idempotency rules already established.

The frozen Architecture Baseline establishes Supabase/PostgreSQL as FootCap's database and authoritative durable data store. It also requires version-controlled migrations, provider-independent domain identity, idempotent ingestion where possible, repository boundaries for Python writes, and a minimum physical schema for source/domain entities and stable/provider identifiers. This ADR narrows those requirements to the first implementable normalized slice.

This ADR does **not** design Match persistence, raw-content or raw-observation persistence, Run provenance persistence, ingestion-target persistence, prediction/model/feature persistence, or a complete production schema.

---

## Decision

Adopt the following persistence semantics for the first normalized core-domain slice.

### 1. Authoritative durable store

PostgreSQL, provided through Supabase, is the authoritative durable store for this slice. This follows the frozen Architecture Baseline and is not a new technology decision.

In-memory domain values and test doubles are not authoritative persistence. A completed durable operation is one whose required database changes committed successfully.

### 2. First persisted slice

The first persisted slice consists of exactly these relations/concepts:

- `competitions`;
- `teams`;
- `seasons`;
- `provider_identity_mappings`.

Season cannot remain transient because the semantic uniqueness and creation idempotency fixed by ADR-014 must survive process restarts and reruns. `ProviderIdentityMapping` cannot remain transient because provider references must resolve consistently across executions and bootstrap must not recreate domain entities after every restart.

Match is explicitly excluded. Match construction still depends on completed Competition, Season, Home Team, and Away Team resolution, and its persistence semantics require a separate later decision.

### 3. Competition persistence semantics

Minimum durable Competition information:

**Required**

- `competition_id`;
- `name`.

**Optional now**

- `country`.

**Deferred**

- competition type;
- provider logo or other presentation metadata;
- other provider metadata.

`competition_id` is the FootCap Competition identity. `name`, `country`, type, logo, and other metadata never establish identity. No semantic uniqueness beyond `competition_id` is introduced; names and countries are not assumed unique.

Provider league IDs must not be stored directly on Competition. Provider identity belongs exclusively in `provider_identity_mappings`.

### 4. Team persistence semantics

Minimum durable Team information:

**Required**

- `team_id`;
- `name`.

**Optional now**

- `country`;
- `national`.

**Deferred**

- code;
- founded year;
- provider logo or other presentation metadata;
- richer provider metadata.

`team_id` is the FootCap Team identity. Team identity is independent of Competition, Season, name, country, code, founded year, national status, and provider presentation metadata. No `competition_id` or Season key belongs on Team itself, and no semantic uniqueness beyond `team_id` is introduced.

Provider team IDs must not be stored directly on Team. They belong exclusively in `provider_identity_mappings`.

### 5. Season persistence semantics

Season has an explicit durable `seasons` relation. Its Phase 0 semantic identity remains exactly:

```text
(competition_id, start_year)
```

No opaque `season_id` is introduced in this slice. Persistence must physically enforce at most one row for an exact `(competition_id, start_year)` pair, with semantics equivalent to `UNIQUE(competition_id, start_year)`. The exact migration syntax remains an implementation detail.

Every Season references an existing Competition through a real database foreign key. Deleting a Competition must not cascade-delete Seasons; the relationship uses restrictive/no-action deletion semantics conceptually. This records the required PostgreSQL behavior without freezing the exact constraint name or DDL spelling.

There is no `is_current`, current/historical discriminator, provider Season reference, or `ProviderIdentityMapping` for Season. Creation authorization remains governed by ADR-014 and is not inferred from the existence or shape of a row.

### 6. Provider identity mapping persistence

The persisted mapping shape is exactly four semantic columns:

```text
provider
entity_type
provider_entity_id
footcap_entity_id
```

The first three columns identify the exact `ProviderEntityRef`; `footcap_entity_id` is the opaque FootCap target ID. Persistence must physically enforce forward uniqueness equivalent to:

```text
UNIQUE(provider, entity_type, provider_entity_id)
```

No reverse uniqueness is permitted. Distinct provider references may map to the same FootCap identity, including within the same provider and entity type. For example, both mappings below remain valid:

```text
("api-football", "team", "505") -> "team-1"
("api-football", "team", "999") -> "team-1"
```

Provider identity fields remain strings with ADR-012 exact-value semantics: no trimming, case folding, numeric reinterpretation, or leading-zero normalization. Consequently, values such as `"505"` and `"0505"` remain distinct.

### 7. Four-column mapping; no `target_entity_type`

ADR-012 deliberately excludes a stored FootCap target type because it is derived from the supported `(provider, entity_type)` correspondence. Persistence preserves that decision and rejects a fifth `target_entity_type` column for this slice.

The comparison is:

| Consideration | Four columns | Five columns with `target_entity_type` |
|---|---|---|
| Current lookup | Fully supports forward resolution | Adds no required lookup capability |
| Target namespace | Derived from the supported correspondence | Duplicates derived information |
| Physical target FK | Cannot provide one polymorphic FK | Still cannot provide one polymorphic FK |
| Integrity risk | One authoritative correspondence | Permits contradictions such as `team` + `competition` |
| Extra enforcement | None beyond correspondence validation | Requires a CHECK or duplicated correspondence table/rule |
| Future Fixture mapping | Already derivable as Fixture to Match | Extra column still adds no target FK |

Debugging convenience is insufficient justification for duplicating semantic information. If future demonstrated query or integrity requirements need a persisted target namespace, that is a reconsideration trigger rather than a speculative Phase 0 column.

### 8. Polymorphic target integrity

`footcap_entity_id` can identify different FootCap namespaces according to the validated provider/type correspondence. Phase 0 does not introduce:

- a common entity-registry table;
- nullable Competition/Team/Match FK columns;
- table inheritance;
- a generic polymorphic database abstraction.

There is no physical FK from `provider_identity_mappings.footcap_entity_id` to Competition, Team, or future Match tables in this slice. The application/storage boundary must derive the expected namespace and verify that the referenced FootCap entity exists before storing the mapping.

Forward mapping uniqueness and target referential integrity are separate concerns. The uniqueness constraint prevents one provider reference from resolving to multiple FootCap identities; it does not prove that the target entity exists in the correct namespace.

**Transactional target validation for supported writes.** Every SUPPORTED mapping write must, inside the same transaction-scoped storage operation as the mapping insertion: (1) derive the supported target namespace from `(provider, entity_type)`; (2) reject an unsupported provider/entity_type correspondence; (3) verify that `footcap_entity_id` exists in the expected FootCap target relation/namespace; and (4) only then persist the mapping as part of that same transaction-scoped operation. A preliminary read performed outside that transaction is not sufficient — it is exactly the kind of stale pre-write check decision 11 already treats as an optimization, not a correctness boundary. For entity-plus-first-mapping creation (decision 10), the newly-created entity row already exists inside that same transaction, so the creation operation itself establishes target existence before the mapping commits. For an additional alias mapping to an already-existing entity, target existence and namespace must be checked transactionally, immediately before the mapping write commits, within that same operation.

**Direct SQL limitation.** PostgreSQL does not physically enforce polymorphic mapping-target referential integrity in this Phase 0 schema. Unrestricted direct or manual SQL against `provider_identity_mappings` could therefore insert a mapping whose `footcap_entity_id` does not exist, or exists only in the wrong FootCap namespace. Such writes are outside the supported persistence boundary described above; the database itself does not prevent them. This does not weaken physical forward uniqueness (decision 6), which remains database-enforced regardless of how a row is written.

**Enforcement boundary.** Database-enforced: provider mapping forward uniqueness; the Season foreign key; Season natural-key uniqueness; entity/mapping transaction atomicity. Application/storage-boundary enforced: supported provider/entity-type correspondence; mapping target namespace; mapping target existence.

If deletion of Competition, Team, or Match is introduced later, deletion semantics must preserve mapping-target integrity, because no physical foreign key currently protects that relationship. This ADR does not design deletion.

### 9. Mapping idempotency and conflict

Persistence preserves ADR-012 behavior:

- absent mapping: insert succeeds;
- existing identical mapping: idempotent success;
- same provider reference mapped to a different FootCap ID: explicit conflict/error;
- no silent remapping or overwrite.

An `ON CONFLICT`-style database mechanism may be used, but exact SQL is not frozen. Blind `DO NOTHING` is insufficient: after a uniqueness conflict, the operation must distinguish an identical replay from a conflicting remap by comparing the existing target ID.

### 10. Entity and first mapping atomicity

Creating a Competition with its first provider mapping and creating a Team with its first provider mapping each require one real PostgreSQL transaction boundary. A successful operation exposes both the entity and mapping, or neither.

Application retries alone do not satisfy ADR-013 atomicity. If entity creation or mapping creation fails, the transaction rolls back the entire logical operation so no newly-created unmapped entity becomes durable.

### 11. Concurrency model

The minimum concurrency strategy is:

- an ordinary PostgreSQL transaction;
- `READ COMMITTED` isolation;
- physical forward uniqueness on `(provider, entity_type, provider_entity_id)`;
- rollback of the losing transaction's newly-created entity when competing writers race.

A pre-write mapping lookup is an optimization, not the correctness boundary. The lookup may become stale immediately. Correctness depends on transaction atomicity, the database uniqueness constraint, and explicit post-conflict classification as idempotent replay or conflicting remap.

`SERIALIZABLE` isolation, advisory locks, distributed locks, and generic locking infrastructure are not required for this slice.

### 12. Season creation atomicity

Season creation is a single persisted Season operation. It requires:

- an existing Competition enforced by the foreign key;
- physical enforcement of the Season natural identity;
- creation authorization supplied and enforced by the trusted calling bootstrap/application context.

Season has no accompanying provider mapping row, so no Season-specific multi-row atomicity mechanism is introduced.

### 13. Authorization is not persisted in this slice

This slice does not add Competition authorization status, Season authorization tables, Team authorization flags, or `ingestion_targets`.

- Competition presence records durable curated existence.
- Season creation authorization belongs to the exact Competition/provider-season ingestion or bootstrap context defined by ADR-014; the Season row records existence, not authorization configuration.
- Team creation authorization belongs to the trusted Competition-bootstrap context defined by ADR-013.

Authorization and existence are distinct. A persisted entity is not a general-purpose authorization rule for creating further entities.

### 14. Initial Serie A curation

Serie A must not be hard-coded into generic domain models, repository logic, or SQL schema primitives. The curated initial Competition should eventually be established through an explicit, repeatable application/Python setup command.

Manual database insertion and product-data seeding embedded in a schema migration are rejected. The command itself is not designed or implemented by this ADR.

### 15. Operational timestamps

Storage rows may contain `created_at` and `updated_at` as persistence-only operational metadata. They are not domain identity and are not `event_at`, `received_at`, or `source_available_at`.

Operational timestamps do not participate in Competition, Team, or Season equality. Whether both timestamps are needed on every table and their exact database defaults remain migration-level choices.

### 16. Deletion and active status

No soft-delete, status, or `is_active` lifecycle is introduced. Provider disappearance does not imply deletion of provider-independent FootCap identity.

Deletion authorization and lifecycle semantics remain deferred. The restrictive Competition-to-Season relationship in decision 5 prevents accidental cascading loss but does not otherwise define a deletion workflow.

### 17. Domain and storage separation

Domain objects express domain semantics. Storage rows may contain persistence-only details such as operational timestamps and physical representation details. Repositories/adapters translate between the two boundaries.

Database-only fields must not be added to domain objects merely because storage retains them. This internal persistence slice creates no cross-language/public boundary and requires no shared-contract change.

### 18. Repository boundary

The intended implementation direction is:

- narrow per-entity persistence adapters/repositories for ordinary reads and writes;
- narrow transaction-scoped application/storage operations for entity-plus-first-mapping creation.

This does not freeze class names, method signatures, protocols, or module layout. A generic Unit of Work abstraction is not required.

### 19. FootCap ID generation

The exact FootCap ID generator remains deferred. This ADR does not select UUID, ULID, database-generated IDs, application-generated IDs, sequences, prefixes, or encodings.

IDs remain opaque and provider-independent. The physical PostgreSQL column type is also deferred to migration design, subject to preserving the established ID semantics.

### 20. Raw and Run persistence boundary

`RawContent`, `RawObservation`, and `RunProvenance` persistence remain separate future tracks. They are not prerequisites for this normalized bootstrap slice, and this ADR does not reopen ADR-011 or ADR-010.

The absence of those tables in the first migration does not weaken their existing semantic requirements or make in-memory observations equivalent to durable raw persistence.

### 21. Minimum future database test matrix

The first migration/persistence implementation must include executable database tests for at least:

1. Competition insertion and duplicate primary-identity rejection.
2. Team plus first mapping atomic success.
3. Mapping failure leaving no orphan Team.
4. Season insertion for an existing Competition.
5. Season insertion failure for a missing Competition.
6. Physical rejection of duplicate Season natural identity.
7. Idempotent replay of an identical mapping.
8. Rejection of a conflicting forward mapping.
9. Acceptance of reverse many-to-one mappings.
10. A concurrent creation race leaving exactly one durable entity/mapping pair.
11. Competition plus first mapping atomic success.
12. Mapping failure leaving no orphan Competition.
13. Rejection of a mapping whose `footcap_entity_id` does not exist in the expected target relation.
14. Rejection of a mapping whose `footcap_entity_id` exists, but only in the wrong FootCap namespace (for example, `entity_type="team"` with a `footcap_entity_id` that is an existing Competition ID, not a Team ID) — critical because no physical polymorphic FK protects this relationship.
15. Rejection of an unsupported provider/entity_type correspondence (for example `("api-football", "season")`, `("api-football", "banana")`, or `("unknown-provider", "team")`) before any durable mapping row is created, without narrowing `ProviderEntityRef`'s structurally-open construction semantics.
16. Exact provider-string treatment: `provider_entity_id="505"` and `provider_entity_id="0505"` persist/resolve as distinct values, and provider values differing only by case remain distinct, with no trimming or normalization.
17. Rejection of Competition deletion while an existing Season still references it, rather than cascading the Season away.

These tests are requirements for future implementation; this ADR creates none.

### 22. First migration scope

The intended first migration contains exactly:

- `competitions`;
- `teams`;
- `seasons`;
- `provider_identity_mappings`.

It contains no Match, raw, Run, ingestion-target, prediction, model, feature, Player, or participation table. This ADR does not create the migration.

---

## Consequences

- Bootstrap identity and Season existence survive process restarts and reruns.
- FootCap domain identity remains independent from provider identifiers.
- Forward provider mapping is deterministic while provider aliases remain representable.
- Database uniqueness and transaction atomicity, rather than stale preliminary reads, provide concurrent-writer correctness.
- Season has real Competition referential integrity without introducing an unnecessary surrogate ID.
- Polymorphic mapping target integrity remains an explicit application/storage-layer obligation because Phase 0 deliberately avoids speculative entity-registry infrastructure. The accepted cost of the four-column design is that this integrity depends on the supported application/storage write boundary, not PostgreSQL alone.
- Raw, Run, Match, and authorization persistence can be designed independently without blocking this small normalized slice.

Costs and accepted limitations:

- `provider_identity_mappings` has no physical target FK, so the storage boundary must validate target existence and namespace; direct/manual SQL that bypasses the supported write boundary is not restricted by PostgreSQL itself.
- The first schema cannot perform generic FK-backed queries across every possible mapped target.
- Concurrent losers may create provisional entity rows inside a transaction, but rollback prevents those rows from becoming durable.
- Authorization configuration is not independently durable or reconstructible yet; it remains caller-owned until a demonstrated operational requirement justifies persistence.

---

## Rejected Alternatives

1. **No Season table** — rejected because Season identity and idempotency must survive process restarts and Match normalization requires durable Season resolution.
2. **Provider IDs stored directly on Competition or Team** — rejected because provider identity belongs in the mapping boundary and aliases/multiple providers must remain possible.
3. **Provider ID reused as FootCap ID** — rejected by ADR-011 through ADR-013; it couples domain identity to a replaceable provider.
4. **Five-column mapping with `target_entity_type`** — rejected because target namespace is already derived, no current physical FK or query requires the column, and the duplicate value creates a new inconsistency without adding integrity.
5. **Reverse mapping uniqueness** — rejected because ADR-012 explicitly permits aliases, including within the same provider/entity type.
6. **Name-based Competition or Team uniqueness** — rejected because mutable/non-unique metadata cannot establish identity.
7. **Team scoped to Competition** — rejected because Team identity is Competition-independent.
8. **Team scoped to Season** — rejected because Team identity persists across Seasons.
9. **Season as `ProviderEntityRef`** — rejected because API-Football Season is provider context, not an independent provider entity.
10. **Season through `ProviderIdentityMapping`** — rejected because no provider Season entity reference exists to map.
11. **Opaque `season_id` now** — rejected because ADR-014 establishes the composite Phase 0 identity and no current consumer requires a surrogate.
12. **Common entity-registry table** — rejected as unnecessary infrastructure solely to manufacture polymorphic target FKs.
13. **Nullable target FK columns per mapped entity type** — rejected because they create sparse rows and complex mutual-exclusion constraints that grow with every entity type.
14. **Table inheritance or generic polymorphic DB abstraction** — rejected because this slice has no demonstrated need for it.
15. **Generic Unit of Work now** — rejected; narrow transaction-scoped operations satisfy the required atomicity with less abstraction.
16. **`SERIALIZABLE` isolation by default** — rejected because transaction atomicity plus physical forward uniqueness is sufficient for this slice.
17. **Advisory or distributed locks** — rejected because database uniqueness resolves the identified race without new locking infrastructure.
18. **Persistent `ingestion_targets` now** — rejected because authorization configuration persistence is outside this slice.
19. **Persistent authorization flags now** — rejected because existence and creation authorization are distinct, and no current consumer requires durable flags.
20. **Match persistence in this slice** — rejected because Match semantics and storage relationships require their own later design.
21. **Raw persistence as a prerequisite** — rejected because ADR-013 already separates raw durability ordering from normalized bootstrap correctness.
22. **Run provenance persistence as a prerequisite** — rejected because Run persistence is a separate track and is not required for core entity/mapping durability.
23. **Hard-coded Serie A schema logic or migration seed** — rejected because product scope must not leak into generic schema and repeatable setup belongs at the application boundary.
24. **Soft-delete/status lifecycle now** — rejected because no current product operation requires it and provider disappearance is not domain deletion.
25. **Metadata-provenance schema now** — rejected because source correction/version and metadata provenance remain open and must not be improvised in this minimal slice.
26. **Blind conflict `DO NOTHING`** — rejected because it cannot distinguish safe idempotent replay from an attempted conflicting remap.
27. **Competition-to-Season cascade deletion** — rejected because deleting a Competition must not silently erase durable Season identity.

---

## Scope / Deferrals

This ADR explicitly defers, without deciding:

- exact FootCap ID generator;
- physical ID column type;
- exact DDL and constraint names;
- Competition type;
- provider logos and presentation metadata;
- Team code;
- Team founded year;
- richer Competition/Team metadata;
- metadata source provenance;
- source correction/version behavior;
- identity correction/reconciliation workflow and mapping history;
- exact repository APIs and protocols;
- exact transaction-service names and module layout;
- exact SQL query and conflict-handling statements;
- Match persistence;
- `RawContent` and `RawObservation` persistence;
- `RunProvenance` persistence;
- Player persistence;
- participation persistence;
- prediction, model, feature, and dataset persistence;
- soft-delete and deletion lifecycle;
- active/tracked lifecycle;
- future persistent authorization/configuration model;
- ingestion-target persistence;
- a future entity registry, if a demonstrated requirement emerges;
- physical target referential-integrity mechanism;
- transaction retry policy;
- operational timestamp selection/defaults;
- RLS and direct-exposure policy for the new relations;
- concrete Serie A setup command;
- concurrency behavior beyond the minimum race invariant above.

---

## Future Reconsideration Triggers

Revisit the relevant narrow decision, without pre-deciding its replacement, if:

- Match persistence requires stronger polymorphic mapping-target integrity.
- A second provider changes the supported correspondence or query assumptions.
- Player mapping introduces materially different target-integrity needs.
- Generic cross-entity mapping queries become a demonstrated requirement.
- Correction/reconciliation requires mapping history or remapping audit.
- Metadata provenance becomes required by a real consumer.
- Operational authorization must survive and be reproducible independently of caller configuration.
- The selected ID generator imposes a concrete physical database representation.
- A soft-delete or tracked/active lifecycle becomes a product requirement.
- Direct browser exposure requires explicit RLS/public-schema decisions.
- Raw, Run, or Match persistence implementation begins.
- Concurrency/load evidence demonstrates `READ COMMITTED` plus uniqueness is insufficient for an identified operation.

No resulting solution is selected by this trigger list.

---

## Architecture and Contract Integrity

This ADR does not modify or reopen the frozen Architecture Baseline or ADR-011 through ADR-014. It creates no shared-contract shape, Python implementation, SQL migration, repository, or dependency. Shared contracts remain unchanged because these persistence rows are internal storage representations rather than a new cross-language/public contract.
