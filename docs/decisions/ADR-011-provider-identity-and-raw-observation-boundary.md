# ADR-011: Provider Identity and Raw Observation Boundary

**Status:** Accepted

**Date recorded:** Phase 0, Task 0.5.1C

**Relation to the Architecture Baseline:** This ADR is a Phase 0 implementation/domain decision and does **NOT** modify or reopen `FOOTCAP_ARCHITECTURE_V1.2.1.md`. The Architecture Baseline remains FROZEN. Frozen semantics already owned by `FOOTCAP_ARCHITECTURE_V1.2.1.md`, ADR-009, ADR-010, and the existing shared contract schemas (`packages/contracts/schemas/*.schema.json`) remain authoritative and are referenced here, not redefined.

---

## Context

Task 0.5.1A produced an initial API-Football provider/ingestion design. An adversarial review (Task 0.5.1A-R) concluded the original design was not ready to implement as a whole, but that enough evidence existed to freeze a narrower decision cluster first: how FootCap represents a provider's own entity identifiers, how it distinguishes those from FootCap domain identity, and how it models a raw provider HTTP response before any of that identity resolves. Task 0.5.1B reconciled both reviews and produced a final, narrow decision set. This ADR records exactly that set.

`FOOTCAP_ARCHITECTURE_V1.2.1.md` already establishes that FootCap `match_id` is provider-independent domain identity (ADR-009 decision 11) and that raw snapshots retain provider, endpoint, parameters, request/receive times, status, response hash, payload, ingestion run ID, and availability evidence (Architecture §5.6, §6). What it leaves open for Phase 0 is the concrete internal shape of a provider entity reference, the boundary between "raw provider response" and "provider-independent normalized fact," and the precise, non-overlapping meaning of a raw observation, its content, and its identity. This ADR resolves exactly those gaps and no others.

---

## Decision

Adopt the twelve decisions below as the Provider Identity and Raw Observation Boundary for Phase 0. No contract files, code, migrations, tests, or dependencies are introduced by this ADR — it records decisions to be executed in subsequent Phase 0 tasks.

### 1. `ProviderEntityRef`

A Python-internal boundary concept, not a shared contract:

```
ProviderEntityRef(
    provider,
    entity_type,
    provider_entity_id,
)
```

It applies only where the provider exposes an actual, provider-assigned entity identifier. For API-Football, `league`, `team`, `fixture`, and `player` are valid `entity_type` values. `season` is not a standalone `ProviderEntityRef` (see decision 3). No shared JSON Schema is introduced for this type.

### 2. Provider identity is never FootCap identity

A provider-assigned ID is never used directly as a FootCap domain ID. Explicitly:

- API-Football fixture ID != FootCap `match_id`
- API-Football league ID != FootCap competition identity
- API-Football team ID != FootCap team identity
- API-Football player ID != FootCap player identity

This extends ADR-009 decision 11 to the full set of provider entity types this ADR recognizes; it does not redecide decision 11. No persistence mapping table is defined here.

### 3. Season

API-Football season is contextual request/domain data represented by a four-digit starting year. It is not treated as a standalone `ProviderEntityRef`, because API-Football exposes no independent, provider-assigned season resource identifier the way it does for leagues, teams, fixtures, and players. FootCap Season persistence identity remains deferred.

### 4. Unresolved identity boundary

Without a resolved FootCap identity, the pipeline may still perform:

- HTTP response receipt;
- exact raw-byte capture;
- `RawObservation` construction;
- provider envelope parsing;
- provider DTO construction.

It must not proceed to:

- a provider-independent normalized FootCap fact;
- `MaterialFact` construction for that fact;
- Temporal Engine evaluation;
- feature/model consumption.

Unresolved mapping is an explicit internal outcome, represented by a small Python-internal type distinguishing a resolved FootCap identity from an explicit unresolved marker carrying the original `ProviderEntityRef`. It must never fabricate a FootCap ID. No shared contract is created for this outcome.

### 5. `RawObservation`

`RawObservation` represents exactly one actual provider HTTP response occurrence. Conceptually it carries enough provenance to identify the observation, including: provider; endpoint; logical request identity/reference; page/HTTP request identity/reference when applicable; request parameters; `requested_at`; `received_at`; HTTP status; `job_run_id`; content fingerprint/reference; and availability evidence/rationale when a source-availability derivation is actually being asserted for this observation. No persistence storage schema is defined. Arbitrary response headers or rate-limit metadata are not required as frozen fields — they are an implementation convenience, not part of this conceptual minimum.

### 6. `RawContent`

`RawContent` is separate from `RawObservation`. It consists conceptually of the exact, immutable HTTP response body bytes, and a content fingerprint computed over those exact bytes. The exact bytes must be captured before JSON parsing. Parsed or re-serialized JSON is never the canonical raw representation, because re-serialization can change byte-for-byte form (key order, whitespace, number/unicode formatting) even when semantically equivalent, silently breaking byte-fidelity and fingerprint reproducibility against what the provider actually sent.

### 7. Observation vs. content invariant

Two `RawObservation`s may contain byte-identical `RawContent`, and therefore an identical content fingerprint, while remaining distinct observations — `requested_at`, `received_at`, `job_run_id`, headers, rate-limit state, execution, and request/page context can all differ independently of body content. Observation provenance must never be collapsed merely because content bytes match. This is a durable invariant.

### 8. Physical deduplication deferred

This ADR does not decide whether identical `RawContent` blobs are stored once, stored multiple times, object-storage deduplicated, or database-deduplicated. That belongs to future persistence design. The only invariant fixed here is decision 7: distinct `RawObservation`s remain distinct regardless of whichever physical storage strategy is later chosen.

### 9. Content fingerprint semantics

Only semantic meaning is frozen: the content fingerprint is computed from exact raw HTTP body bytes and is an integrity/content-address fingerprint. It is explicitly **not**: `RawObservation` identity, request identity, provider entity identity, FootCap domain identity, or proof of semantic equivalence between two responses. The hash algorithm is not fixed by this decision, and no specific Python field name is required.

### 10. Request identity layering

Two distinct conceptual identities are recorded:

- **Logical request identity** = provider + endpoint + normalized semantic filters. It excludes credentials, execution timestamp, retry attempt, and pagination page.
- **Page/HTTP request identity** = identifies the individual HTTP call/page within a logical request series.

No universal parameter canonicalization algorithm is defined here (see decision 11).

### 11. Parameter normalization scope

Request identity must be based on normalized semantic parameters. Exact parameter canonicalization is endpoint-specific and deferred to implementation, because API-Football's parameter shapes are not uniform across endpoints. No cross-endpoint canonicalization rules are defined by this ADR.

### 12. Source availability

No new temporal rule is created. This ADR references Architecture §5.4 only:

- Historical/backfill without independent evidence: `source_available_at` = UNKNOWN/null.
- Prospective live-collected fact: `source_available_at` = `received_at` unless documented evidence supports another instant.

`received_at` and `source_available_at` remain semantically distinct fields even when their values are equal — a consumer must always read `source_available_at` for temporal-eligibility purposes and must never treat `received_at` as an acceptable substitute merely because the two happened to match. `EVENT_TIME_SAFE` and `KNOWLEDGE_TIME_VERIFIED` are not redefined by this ADR.

---

## Consequences

- `ProviderEntityRef`, `RawObservation`, `RawContent`, and the request-identity concepts above are Python-internal for Phase 0; nothing here requires a change to `packages/contracts/schemas/*` (no cross-language consumer for these concepts has been identified).
- Any future ingestion code that resolves provider identity must represent an unresolved outcome explicitly rather than substituting a provider ID or a fabricated placeholder for a missing FootCap ID.
- Any future raw-capture code must capture bytes before parsing and must never reconstruct "raw" content from a parsed/re-serialized representation.
- Any future observation-tracking code must not deduplicate or merge observations on content match alone; repeated identical-content observations remain individually traceable.
- Historical/backfilled API-Football data ingested under this ADR will carry `source_available_at` = UNKNOWN unless live-collection evidence applies, which — per the already-frozen Temporal Engine — means such data can support `EVENT_TIME_SAFE` classification but not `KNOWLEDGE_TIME_VERIFIED` without independently obtained availability evidence. This is a traced consequence of already-frozen rules, not a new one.
- A subsequent implementation task may build the HTTP client, retry/rate-limit/pagination behavior, provider DTOs, and identity-resolution code against this boundary without re-deciding what is fixed here.

---

## Rejected Alternatives

1. **API-Football provider IDs used directly as FootCap IDs** — rejected; couples FootCap domain identity to a specific, replaceable provider, contradicting ADR-009 decision 11 and the Master Brief's provider-replaceability goal.
2. **Season treated as a standalone `ProviderEntityRef`** — rejected; API-Football exposes no independent, provider-assigned season identifier to anchor one.
3. **Unresolved identity fabricating a FootCap ID** — rejected; would silently misrepresent an unmapped record as a resolved one.
4. **Normalization proceeding before identity resolution** — rejected; a "provider-independent normalized fact" is by definition FootCap-identified, so its construction must be gated on the resolution outcome.
5. **Parsed/re-serialized JSON replacing exact raw bytes as the canonical raw representation** — rejected; breaks byte-fidelity and fingerprint reproducibility.
6. **Identical content collapsing distinct `RawObservation`s** — rejected; would silently lose execution-level provenance and audit trail.
7. **Content fingerprint used as observation, request, provider, or domain identity** — rejected; it is an integrity/content-address value only.
8. **One universal parameter canonicalizer defined before endpoint-specific needs are known** — rejected; API-Football's parameter shapes are not uniform across endpoints, so a premature universal canonicalizer would either be trivially useless or overbuilt.
9. **Broad normalized-domain idempotency frozen in Phase 0** — rejected as premature; upsert keys, correction/version policy, and database uniqueness constraints depend on persistence design that does not exist yet.

---

## Scope

This ADR governs only the twelve decisions above. It explicitly does **not** design:

- an HTTP client;
- `httpx` or any other HTTP library choice;
- authentication mechanics;
- retry behavior or a retryable-failure taxonomy;
- rate-limit handling;
- pagination mechanics;
- endpoint-specific DTOs;
- persistence (schema, storage, or otherwise);
- serialization;
- polling or scheduling;
- orchestration or partial-failure coordination;
- normalized-domain idempotency (upsert keys, correction/version policy, database uniqueness constraints).

It also explicitly defers, without deciding: persistence schema; physical `RawContent` deduplication; normalized-domain upsert/idempotency; source-fact correction/version policy; database uniqueness constraints; universal request canonicalization; the hash algorithm; retry taxonomy; rate-limit policy; pagination architecture; polling schedule; partial-failure coordination; RunStatus mapping; match-event `event_at` derivation; FootCap season persistence identity; and HTTP library choice.

It does not change any invariant, entity, classification, or lifecycle rule defined in `FOOTCAP_ARCHITECTURE_V1.2.1.md`, and it does not redefine anything already frozen by ADR-009 or ADR-010.

---

## Future Reconsideration Triggers

This ADR should be revisited, not silently reinterpreted, if any of the following occur:

- A second data provider is added — tests whether `ProviderEntityRef`'s shape generalizes beyond API-Football.
- A persistence schema for raw observations/content is implemented — may require revisiting the exact `RawObservation` field list against real storage constraints.
- Raw content moves to object storage rather than an inline representation — may affect what "content fingerprint/reference" means practically.
- A cross-language consumer needs provider/raw concepts — triggers promoting something into `packages/contracts/`.
- Source-fact correction/version policy is designed (already an open Architecture item, §31.2).
- Event ingestion is implemented — triggers the deferred match-event `event_at` derivation decision.
- API-Football is found to expose a genuine independent season entity/identifier in the future — would revisit decision 3.

No resulting solution for any of these triggers is pre-decided by this ADR.
