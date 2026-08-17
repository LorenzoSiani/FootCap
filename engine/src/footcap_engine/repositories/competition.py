"""
Competition repository and atomic-creation contracts (Task 0.5.11A;
restructured by Task 0.5.11A.1 Fix 1).

Contract only -- no PostgreSQL, no SQL, no connection/cursor, no Supabase
concept appears anywhere in this module. A future implementation must
translate any database-specific failure into the errors declared in
footcap_engine.repositories.errors before it reaches a caller.

Two separate, narrow protocols, per ADR-015's own distinction:
- CompetitionRepository: ordinary reads/writes (here, just a read --
  Competition creation is curated/explicit, ADR-013 decision 2, so there
  is no bare mapping-less write operation with a current use case).
- CompetitionMappingCreation: the one narrow, transaction-scoped
  operation for entity-plus-first-mapping creation (ADR-013 decision 7).
  Kept as its own protocol, not a method on CompetitionRepository,
  because it is a fundamentally different persistence boundary (it
  durably touches two tables atomically) with different callers than
  ordinary Competition reads -- exactly the distinction ADR-015 itself
  draws between "narrow per-entity repositories/adapters for ordinary
  reads/writes" and "narrow transaction-scoped operations for
  entity-plus-first-mapping creation". This is not a generic
  UnitOfWork/transaction manager -- it has exactly one fixed operation,
  scoped to exactly Competition + its mapping, with no caller-visible
  transaction control.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.competition import Competition
from ..domain.identity import ProviderEntityRef


@runtime_checkable
class CompetitionRepository(Protocol):
    """Durable persistence boundary for ordinary Competition reads
    (ADR-013; ADR-015 decision 3). `@runtime_checkable` here only
    verifies that an object exposes methods of these names -- it does
    NOT check parameter or return types; real conformance is a
    static-typing concern."""

    def get(self, competition_id: str) -> Competition | None:
        """Return the Competition with this exact id, or None if no such
        Competition exists. Ordinary identity lookup -- absence is an
        expected outcome, never an error."""
        ...


@runtime_checkable
class CompetitionMappingCreation(Protocol):
    """The single, narrow, transaction-scoped Competition-plus-first-
    provider-mapping creation operation (ADR-013 decision 7). Persistence-
    facing only -- it owns no authorization decision. Whether this call
    should happen at all (ADR-013 decision 2: Competition creation is
    curated/explicit) is decided entirely by the caller/application
    layer before this operation is ever invoked; no authorization flag
    or context object is accepted here.
    `@runtime_checkable` here only verifies that an object exposes
    methods of these names -- it does NOT check parameter or return
    types; real conformance is a static-typing concern."""

    def create_with_mapping(self, competition: Competition, provider_ref: ProviderEntityRef) -> Competition:
        """Durable outcome is determined entirely by existing state,
        exactly one of:

        Case A -- competition.competition_id does not yet exist, AND
        provider_ref is not yet mapped to anything: create both
        atomically (a successful call durably persists both, or
        neither); return the newly created Competition.

        Case B -- competition.competition_id already exists AND
        provider_ref is already mapped to that exact
        competition.competition_id: idempotent replay. Return the
        existing Competition unchanged; mutate nothing; raise nothing.
        (Because entity-plus-first-mapping creation is always atomic and
        entities are never deleted, "provider_ref is mapped to X"
        already implies "X durably exists" -- there is no case where the
        mapping exists but its target does not.)

        Case C -- provider_ref is already mapped to a FootCap entity id
        OTHER than competition.competition_id: raise
        ProviderMappingConflictError. This is the expected outcome of
        the Task 0.5.10G concurrent-creation race; a caller receiving it
        should call ProviderIdentityMappingRepository.resolve(provider_ref)
        rather than retry this call.

        Case D -- competition.competition_id already exists, but Case B's
        exact replay condition does not hold (e.g. the id exists but
        provider_ref has no mapping at all yet): raise
        EntityAlreadyExistsError. This signals a caller error: either a
        reused competition_id, or the caller should have called
        ProviderIdentityMappingRepository.add_mapping to alias an
        additional provider reference to an already-existing Competition,
        not this creation operation.

        provider_ref must resolve to the Competition correspondence
        (ADR-012 decision 3: provider entity_type "league"); an
        implementation constructs the mapping as
        ProviderIdentityMapping(provider_ref, competition.competition_id)
        internally, so an unsupported correspondence surfaces as that
        constructor's own IdentityInputError -- this contract never
        re-validates or invents a separate error for that case."""
        ...
