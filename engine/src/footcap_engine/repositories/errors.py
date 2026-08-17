"""
Repository-contract error taxonomy (Task 0.5.11A; tightened by Task
0.5.11A.1).

These represent outcomes the repository CONTRACT itself anticipates --
they are distinct from two other error families that must never be
confused with them:

- Domain-layer construction errors (CompetitionInputError, TeamInputError,
  SeasonInputError, IdentityInputError, defined alongside their own value
  objects in footcap_engine.domain) fire when a caller tries to construct
  an invalid Competition/Team/Season/ProviderEntityRef/
  ProviderIdentityMapping in the first place -- before any repository
  operation is ever called. Repositories never re-validate what the
  domain layer already guarantees; in particular, an unsupported
  provider/entity_type correspondence is never a repository-layer
  concern -- it already fails at ProviderIdentityMapping construction.
- Database-implementation-specific errors (e.g. a psycopg exception) must
  never reach a caller through this contract. Translating a concrete
  database failure into one of the errors below is an implementation's
  responsibility, not part of this contract.

Every error below has at least one currently legitimate contract
operation that can raise it (Task 0.5.11A.1 Fix 6) -- none is kept merely
because an earlier revision defined it.
"""
from __future__ import annotations

from ..domain.identity import ProviderEntityRef


class RepositoryError(Exception):
    """Base class for every error a repository-contract operation may
    raise. Never raised directly -- always one of the specific
    subclasses below."""


class EntityAlreadyExistsError(RepositoryError):
    """An entity-plus-first-mapping creation operation's requested
    entity identity (competition_id/team_id) already durably exists, AND
    the request is not the exact idempotent-replay case (see
    CompetitionMappingCreation.create_with_mapping /
    TeamMappingCreation.create_with_mapping for the precise Case
    A/B/C/D decision tree this implements).

    This is deliberately narrower than "the id exists": if the id
    exists AND the exact same provider reference is already mapped to
    it, that is idempotent success (nothing is raised) -- this error
    fires only for the remaining, genuinely ambiguous case, where the
    caller has either reused an identity or should have called
    ProviderIdentityMappingRepository.add_mapping to alias an
    additional provider reference to an entity that already exists,
    not a creation operation."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(f"{entity_type} with id {entity_id!r} already exists")
        self.entity_type = entity_type
        self.entity_id = entity_id


class ReferencedEntityNotFoundError(RepositoryError):
    """An operation referenced another entity that does not exist --
    for example SeasonRepository.get_or_create referencing a Competition
    (ADR-014 decision 11), or ProviderIdentityMappingRepository.add_mapping
    whose target FootCap entity does not exist in the namespace implied
    by the mapping's provider/entity_type correspondence (ADR-015
    decision 8; Task 0.5.8D). Abstracts the underlying foreign-key/
    existence relationship; no PostgreSQL-specific exception is ever
    exposed through this contract."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(f"referenced {entity_type} {entity_id!r} does not exist")
        self.entity_type = entity_type
        self.entity_id = entity_id


class ProviderMappingConflictError(RepositoryError):
    """The exact ProviderEntityRef this operation attempted to map is
    already durably mapped to a DIFFERENT FootCap entity id than the one
    requested.

    This means only that -- an identical existing mapping (the same
    provider_ref already mapped to the same requested FootCap entity id)
    is idempotent success and must never raise this error; only a
    genuine target mismatch does.

    This is the ordinary, expected outcome of the concurrent-creation
    race Task 0.5.10G proved on real PostgreSQL (ADR-013 decision 7;
    ADR-015 decision 11: READ COMMITTED plus the mapping table's primary
    key plus whole-transaction rollback of the loser). When two callers
    race to create or map the same provider reference to two different
    targets, the losing caller receives exactly this error and is
    expected to call ProviderIdentityMappingRepository.resolve()/lookup()
    to obtain the winner's FootCap entity id -- never to retry the
    create/add directly. Preserves ADR-012 decision 7 (forward
    uniqueness), decision 8 (no reverse uniqueness -- distinct provider
    references may still legitimately map to the same FootCap entity;
    that is never a conflict), and decision 10 (no silent remapping)."""

    def __init__(self, provider_ref: ProviderEntityRef) -> None:
        super().__init__(f"provider reference {provider_ref!r} is already mapped to a different FootCap entity id")
        self.provider_ref = provider_ref
