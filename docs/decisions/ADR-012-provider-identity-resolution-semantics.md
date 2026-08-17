# ADR-012: Provider Identity Resolution Semantics

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.5.5B

**Relation to the Architecture Baseline:** This ADR is a Phase 0 implementation/domain decision and does **NOT** modify or reopen `FOOTCAP_ARCHITECTURE_V1.2.1.md`. The Architecture Baseline remains FROZEN. ADR-011 remains authoritative for the raw/provider identity boundary; this ADR does not redefine it, only builds on it. Frozen semantics already owned by `FOOTCAP_ARCHITECTURE_V1.2.1.md`, ADR-009, ADR-010, ADR-011, or the existing shared contract schemas (`packages/contracts/schemas/*.schema.json`) remain authoritative and are referenced here, not restated or redecided.

---

## Context

FootCap provider DTOs (Task 0.5.1D, 0.5.3B, 0.5.4B) now retain provider-owned identifiers for league, team, and fixture entities fetched from API-Football. ADR-011 already establishes that a provider-assigned ID is never used directly as a FootCap domain ID (decision 2) and defines `ProviderEntityRef` as the Python-internal concept naming a provider's own entity identifier (decision 1). What ADR-011 leaves open is how those provider references are actually resolved to stable, provider-independent FootCap domain identities.

Task 0.5.5A produced a read-only design review of that resolution boundary; its adversarial review (Task 0.5.5A.1) concluded the design was correct with changes, now folded into the decisions below. This ADR records only identity-resolution semantics: the shape of a provider-to-FootCap mapping, its cardinality and uniqueness rules, its correction policy, and the strict-resolution behavior an identity resolver must expose.

It does **not** design:

- entity creation;
- FootCap ID generation;
- persistence (schema, storage, or otherwise);
- migrations;
- normalization (e.g. `normalize_fixture_to_match`);
- season identity/resolution;
- mapping audit history;
- provider bootstrap jobs.

---

## Decision

Adopt the sixteen decisions below as the Provider Identity Resolution Semantics for Phase 0. No code, tests, migrations, or dependencies are introduced by this ADR — it records decisions to be executed in a subsequent Phase 0 implementation task.

### 1. `ProviderEntityRef`

`ProviderEntityRef` is a Python-internal semantic identity value, per ADR-011 decision 1:

```
ProviderEntityRef(
    provider: str,
    entity_type: str,
    provider_entity_id: str,
)
```

Semantics:

- immutable value;
- all fields non-blank strings;
- comparison is exact and case-sensitive;
- values are preserved exactly as supplied;
- the generic identity type performs NO trimming, NO case folding, NO numeric parsing, NO leading-zero normalization.

Therefore `"505" != "0505"`, and `"api-football" != "API-FOOTBALL"`.

Provider-specific adapters/boundaries are responsible for converting their native ID representation into the canonical string they intend to use. For API-Football integer IDs, `str(provider_integer_id)` is the canonical conversion. `provider_entity_id` must not be made numeric.

### 2. Open reference vocabulary, validated correspondence

`ProviderEntityRef.provider` and `entity_type` remain open non-blank strings. No shared Enum or Literal is introduced for either field — this preserves the ability to add a second provider or a new entity type without a type change (ADR-011's own Future Reconsideration Triggers already anticipate a second provider).

However, a structurally valid `ProviderEntityRef` is **not** automatically a valid semantic mapping. Identity mapping/resolution must validate that the `(provider, entity_type)` pair has a supported correspondence to a FootCap target type (decision 3). This prevents arbitrary values such as `("api-football", "banana")` from entering valid mappings, while preserving future extensibility of the vocabulary itself.

### 3. Current supported correspondence

Phase 0 supported mapping correspondences:

| `provider` | `entity_type` | FootCap target |
|---|---|---|
| `api-football` | `league` | Competition |
| `api-football` | `team` | Team |
| `api-football` | `fixture` | Match |

`ProviderEntityRef` uses provider-facing entity vocabulary — therefore `entity_type="fixture"`, not `entity_type="match"`. The target FootCap namespace is derived from the supported provider/type correspondence, not stored redundantly on the reference or the mapping (decision 6).

ADR-011 decision 1 recognizes `player` as a possible provider entity type, but player identity resolution is not part of this Phase 0 implementation until a consumer requires it.

### 4. Season exclusion

Season is explicitly not a `ProviderEntityRef` in Phase 0. Per ADR-011 decision 3, API-Football season is contextual starting-year data, not an independent provider-assigned resource identifier. A construction such as `ProviderEntityRef(entity_type="season", provider_entity_id="2026")` is not valid under this semantic model. Season identity/resolution remains deferred; no future season resolution key (e.g. a `(competition_id, season_year) → season_id` mapping) is frozen by this ADR.

### 5. FootCap ID type

FootCap entity IDs remain opaque non-blank strings, following the shared `Identifier` abstraction (`definitions.schema.json`). No UUID, ULID, sequence, database ID, prefix, or encoding is imposed.

### 6. `ProviderIdentityMapping`

The semantic mapping shape:

```
ProviderIdentityMapping(
    provider_ref: ProviderEntityRef,
    footcap_entity_id: str,
)
```

No duplicated `footcap_entity_type` field. The target FootCap namespace is derived from the validated provider/entity_type correspondence (decision 3). Opaque textual FootCap IDs may overlap across namespaces without ambiguity, because interpreting a mapping always includes that derived target namespace alongside the raw ID string.

### 7. Forward uniqueness

Hard invariant: one exact `ProviderEntityRef` resolves to at most one FootCap entity identity. A provider reference must never resolve nondeterministically to multiple FootCap identities.

Future persistence should eventually enforce semantic uniqueness equivalent to `UNIQUE(provider, entity_type, provider_entity_id)`. No physical database schema is defined here.

### 8. No reverse uniqueness

This is critical: this ADR does **not** require that one FootCap entity have at most one provider reference. Multiple `ProviderEntityRef`s may map to the same FootCap entity — across different providers, within the same provider, and within the same provider/entity_type.

Reason: provider identifiers are external and may be replaced, corrected, merged, recreated, aliased, or historically superseded. FootCap domain identity must remain stable even if an external provider identity changes.

Therefore this ADR must not be read as implying a future constraint equivalent to `UNIQUE(provider, entity_type, footcap_entity_id)`. Multiple provider references may intentionally target one FootCap identity; this is allowed cardinality, not automatic deduplication.

### 9. Idempotent same mapping

Semantic storage behavior, once mutable storage exists:

- `store(ref, A)` when `ref` is absent → success.
- `store(ref, A)` when `ref` is already mapped to `A` → idempotent success.
- `store(ref, B)` when `ref` is already mapped to `A` (`A != B`) → conflict.

Repeated storage of the exact same mapping must be safe for retryable bootstrap/ingestion behavior. A conflicting overwrite must never happen silently.

### 10. Correction policy

No silent remapping. If an existing provider reference must change from FootCap entity A to FootCap entity B, that requires a future, explicit correction mechanism — this ADR does not design a replacement API, correction history, versioning, audit tables, or admin workflow for it.

This does not imply mappings are physically immutable forever. The semantic rule fixed here is narrower: no silent conflicting overwrite.

### 11. Strict resolution

The primary identity-resolution operation is strict: `resolve(provider_ref) → FootCap entity ID`. If `provider_ref` is unknown, it raises an explicit unresolved-identity error carrying the exact original `ProviderEntityRef`. An implementation may call this `UnresolvedProviderIdentityError`, but the exact class/module placement is an implementation detail and is not frozen by this ADR.

Unresolved resolution must not be represented as `None` returned from the primary normalization-facing operation.

### 12. Unresolved boundary

This references ADR-011 decision 4 rather than redefining it. The concrete consequence for resolution: unresolved provider identity is acceptable through HTTP response receipt, `RawContent`, `RawObservation`, provider envelope parsing, and provider DTO construction. It must block construction of provider-independent normalized FootCap facts.

Therefore strict identity resolution fails before normalized Match/Team/Competition facts are constructed. No unresolved placeholder FootCap ID is introduced.

### 13. Resolution only

Phase 0 identity implementation is resolution-only. It does not automatically create FootCap entities, generate FootCap IDs, create missing mappings, upsert entities, or persist mappings. Entity creation and mapping bootstrap are separate future decisions (see Scope / Deferrals).

### 14. Fixture / team / competition resolution

- API-Football fixture ID → FootCap Match identity.
- API-Football team ID → FootCap Team identity.
- API-Football league ID → FootCap Competition identity.

The fixture identity key is only the provider-assigned fixture identity:

```
provider="api-football"
entity_type="fixture"
provider_entity_id=str(provider_fixture_id)
```

League, season, home team, away team, and kickoff are not added to the provider fixture identity key. Those are provider facts/consistency evidence (already enforced at the DTO layer per Task 0.5.4B/0.5.4D), not identity components.

### 15. Raw observation exclusion

`ProviderIdentityMapping` does not contain `RawObservation`. `RawObservation` represents one HTTP occurrence (ADR-011 decision 5); identity mapping represents a durable correspondence that may be confirmed by many observations over time. Future mapping creation/correction audit provenance may reference raw or job provenance separately, but that is not part of the semantic identity mapping itself.

### 16. Job run exclusion

`job_run_id` is not part of `ProviderEntityRef`, `ProviderIdentityMapping`, or mapping uniqueness. Different runs must resolve the same provider reference consistently. Execution provenance remains governed by ADR-010.

---

## Implementation Details Not Frozen

The following are explicitly left as implementation choices, not decided by this ADR:

- dataclass versus another immutable representation;
- exact exception class/module;
- class versus function resolver API;
- `resolve()` method name;
- constructor signature;
- Python package path;
- internal dict/index structure;
- a repository protocol/interface, if any, and its shape;
- an in-memory repository implementation, if any;
- repository APIs;
- test organization;
- runtime performance;
- exact persistence schema.

None of these are architectural errors if chosen during implementation — they are simply not ADR decisions.

---

## Consequences

- Provider independence: FootCap domain identity does not depend on any single provider's ID scheme, and a provider reference can be corrected or replaced without changing the FootCap entity it targets.
- Deterministic resolution: a given `ProviderEntityRef` always resolves to the same FootCap entity or fails explicitly; it never resolves ambiguously.
- Safe provider aliases/history: because reverse uniqueness is not required (decision 8), multiple provider references — including historical or superseded ones — may target one stable FootCap entity.
- No silent identity fabrication: unresolved references raise rather than producing a placeholder ID (decisions 11, 12).
- Clean separation from raw provenance: mappings are independent of any single `RawObservation` or `job_run_id` (decisions 15, 16), keeping durable identity separate from point-in-time execution facts.
- Compatible with future multiple providers: nothing in this model assumes API-Football is the only provider.

Costs:

- Mappings must be populated separately from resolution itself; this ADR does not solve how (see Scope / Deferrals).
- Unresolved identities block normalization, meaning ingestion for previously-unmapped entities cannot produce normalized facts until a mapping exists.
- Alias correctness (decision 8's flexibility) requires curated mapping/bootstrap logic to avoid accidentally mapping two distinct FootCap entities together.
- Persistence and correction workflow remain future work; this ADR only fixes the semantic model they must eventually satisfy.

---

## Rejected Alternatives

1. **Using provider IDs directly as FootCap IDs** — rejected; couples FootCap domain identity to a specific, replaceable provider, contradicting ADR-009 decision 11 and ADR-011 decision 2.
2. **Making `provider_entity_id` an int globally** — rejected; would not generalize to a future provider whose native IDs are non-numeric, and reintroduces the exact churn ADR-011 decision 1's string choice already avoids.
3. **Closed global provider/entity-type Enum** — rejected; would require a type change for every new provider or entity type, contradicting the open-vocabulary precedent already set by ADR-009 decision 9.
4. **Storing FootCap target type redundantly in every mapping** — rejected; the target namespace is always derivable from the validated provider/entity_type correspondence (decision 3), so a redundant field would only need its own consistency invariant for no benefit.
5. **Allowing one `ProviderEntityRef` to resolve to multiple FootCap IDs** — rejected; resolution must be deterministic (decision 7), and non-deterministic resolution would silently corrupt downstream normalized facts.
6. **Enforcing reverse uniqueness within provider/entity_type** — rejected; would prevent legitimate provider ID replacement/correction/aliasing from ever mapping to the same stable FootCap entity (decision 8).
7. **Returning `None` silently from strict normalization-facing resolution** — rejected; a caller that forgets to check would silently construct a normalized fact with a missing identity, exactly the class of silent corruption ADR-011 exists to prevent (decision 11).
8. **Automatically creating FootCap entities during resolution** — rejected; would collapse resolution, ID generation, and persistence design into one decision before any of the latter two exist (decision 13).
9. **Silently overwriting conflicting mappings** — rejected; would allow an erroneous re-mapping to corrupt an existing correct one without any signal (decision 10).
10. **Treating season year as `ProviderEntityRef`** — rejected; API-Football exposes no independent, provider-assigned season identifier to anchor one (ADR-011 decision 3; decision 4 above).
11. **Embedding `RawObservation` in mapping semantics** — rejected; conflates a durable correspondence with a single point-in-time HTTP occurrence (decision 15).
12. **Making `job_run_id` part of identity** — rejected; execution provenance and domain-fact identity are already kept separate by ADR-010, and mapping resolution must be run-independent (decision 16).

Repository protocols or other implementation-level abstractions are not rejected as architectural errors by this ADR; they are simply out of scope for an ADR decision (see Implementation Details Not Frozen).

---

## Scope / Deferrals

This ADR governs only the sixteen decisions above. It explicitly defers, without deciding:

- FootCap entity creation;
- FootCap ID generation;
- mapping bootstrap;
- durable persistence schema;
- reverse lookup API;
- mapping correction/version history;
- audit provenance fields;
- season identity/resolution;
- normalized Match construction;
- ingestion orchestration;
- multi-provider registry architecture;
- player resolution;
- provider mapping UI/admin tooling.

It does not change any invariant, entity, classification, or lifecycle rule defined in `FOOTCAP_ARCHITECTURE_V1.2.1.md`, and it does not redefine anything already frozen by ADR-009, ADR-010, or ADR-011.

---

## Future Reconsideration Triggers

This ADR should be revisited, not silently reinterpreted, if any of the following occur:

- A second provider integration begins — tests whether the correspondence table (decision 3) and forward-uniqueness key generalize beyond API-Football.
- Player identity resolution becomes required by a real consumer.
- A persistence schema for mappings is introduced — may require revisiting the exact `ProviderIdentityMapping` field list against real storage constraints.
- A correction/remapping workflow is needed — triggers designing the mechanism decision 10 defers.
- Reverse lookup (FootCap entity → provider references) becomes a real consumer need.
- Season identity design begins.
- Normalized Match construction begins, and exercises the resolution boundary (decision 12) against real fixture/team/competition data end-to-end.
- Provider semantics reveal that entity IDs are not stable enough for the current forward-uniqueness assumption (decision 7).

No resulting solution for any of these triggers is pre-decided by this ADR.
