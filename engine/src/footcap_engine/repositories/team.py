"""
Team repository and atomic-creation contracts (Task 0.5.11A; restructured
by Task 0.5.11A.1 Fix 1).

Contract only -- no PostgreSQL, no SQL, no connection/cursor, no Supabase
concept appears anywhere in this module.

Mirrors competition.py's shape exactly: TeamRepository for ordinary
reads, TeamMappingCreation as its own separate, narrow, transaction-
scoped protocol for the one entity-plus-first-mapping creation
operation -- not a method on TeamRepository, and not a generic
UnitOfWork/transaction manager. See competition.py's module docstring
for the full ADR-015 rationale for this split.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.identity import ProviderEntityRef
from ..domain.team import Team


@runtime_checkable
class TeamRepository(Protocol):
    """Durable persistence boundary for ordinary Team reads (ADR-013;
    ADR-015 decision 4). `@runtime_checkable` here only verifies that an
    object exposes methods of these names -- it does NOT check parameter
    or return types; real conformance is a static-typing concern."""

    def get(self, team_id: str) -> Team | None:
        """Return the Team with this exact id, or None if no such Team
        exists. Ordinary identity lookup -- absence is an expected
        outcome, never an error."""
        ...


@runtime_checkable
class TeamMappingCreation(Protocol):
    """The single, narrow, transaction-scoped Team-plus-first-provider-
    mapping creation operation (ADR-013 decision 7). Persistence-facing
    only -- it owns no authorization decision. Whether this call should
    happen at all -- that it occurs only within an already-authorized
    Competition-bootstrap discovery context (ADR-013 decision 3) -- is
    decided entirely by the caller/application layer before this
    operation is ever invoked; that authorization is deliberately not
    persisted (ADR-013 decision 13) and no authorization flag or context
    object is accepted here.
    `@runtime_checkable` here only verifies that an object exposes
    methods of these names -- it does NOT check parameter or return
    types; real conformance is a static-typing concern."""

    def create_with_mapping(self, team: Team, provider_ref: ProviderEntityRef) -> Team:
        """Durable outcome is determined entirely by existing state,
        exactly one of:

        Case A -- team.team_id does not yet exist, AND provider_ref is
        not yet mapped to anything: create both atomically (a successful
        call durably persists both, or neither); return the newly
        created Team.

        Case B -- team.team_id already exists AND provider_ref is
        already mapped to that exact team.team_id: idempotent replay.
        Return the existing Team unchanged; mutate nothing; raise
        nothing. (Because entity-plus-first-mapping creation is always
        atomic and entities are never deleted, "provider_ref is mapped
        to X" already implies "X durably exists".)

        Case C -- provider_ref is already mapped to a FootCap entity id
        OTHER than team.team_id: raise ProviderMappingConflictError.
        This is the expected outcome of the Task 0.5.10G concurrent-
        creation race, empirically proven for exactly this Team-plus-
        first-mapping shape; a caller receiving it should call
        ProviderIdentityMappingRepository.resolve(provider_ref) rather
        than retry this call.

        Case D -- team.team_id already exists, but Case B's exact replay
        condition does not hold (e.g. the id exists but provider_ref has
        no mapping at all yet): raise EntityAlreadyExistsError. This
        signals a caller error: either a reused team_id, or the caller
        should have called ProviderIdentityMappingRepository.add_mapping
        to alias an additional provider reference to an already-existing
        Team, not this creation operation.

        provider_ref must resolve to the Team correspondence (ADR-012
        decision 3: provider entity_type "team"); an implementation
        constructs the mapping as
        ProviderIdentityMapping(provider_ref, team.team_id) internally,
        so an unsupported correspondence surfaces as that constructor's
        own IdentityInputError -- this contract never re-validates or
        invents a separate error for that case.

        This operation never accepts or stores any competition_id/season
        reference -- Team identity is Competition- and Season-independent
        (ADR-013 decision 4)."""
        ...
