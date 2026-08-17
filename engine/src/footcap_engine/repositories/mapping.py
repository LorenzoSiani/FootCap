"""
Provider identity mapping repository contract (Task 0.5.11A; add_mapping
semantics tightened by Task 0.5.11A.1 Fix 4).

Contract only -- no PostgreSQL, no SQL, no connection/cursor, no Supabase
concept appears anywhere in this module.

resolve()/lookup() are the durable-storage counterpart to the existing,
in-memory IdentityResolver (ADR-012 decision 11; Task 0.5.5D) -- same
two-tier contract, same reused UnresolvedProviderIdentityError, now
backed by persistence instead of a fixed in-memory snapshot.
IdentityResolver itself is not replaced or modified by this contract; it
remains useful wherever a fixed, already-known snapshot of mappings is
resolved repeatedly without further storage round-trips.

No target_entity_type field or parameter appears anywhere in this
contract -- ADR-012 decision 6/ADR-015 decision 7 derive the target
namespace from (provider, entity_type) alone.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.identity import ProviderEntityRef, ProviderIdentityMapping, UnresolvedProviderIdentityError

__all__ = ["ProviderIdentityMappingRepository", "UnresolvedProviderIdentityError"]


@runtime_checkable
class ProviderIdentityMappingRepository(Protocol):
    """Durable persistence boundary for ProviderIdentityMapping
    (ADR-012). `@runtime_checkable` here only verifies that an object
    exposes methods of these names -- it does NOT check parameter or
    return types; real conformance is a static-typing concern."""

    def resolve(self, provider_ref: ProviderEntityRef) -> str:
        """Return the FootCap entity id durably mapped to provider_ref.
        Raises UnresolvedProviderIdentityError (the same type
        IdentityResolver.resolve() raises, re-exported here for
        convenience) if no mapping exists -- never returns None, never
        fabricates or substitutes an id (ADR-012 decision 11; ADR-011
        decision 4). Task 0.5.11B confirmed this reuse; it is not
        replaced by a new repository-specific error."""
        ...

    def lookup(self, provider_ref: ProviderEntityRef) -> str | None:
        """Return the FootCap entity id durably mapped to provider_ref,
        or None if unmapped. Never raises. A soft-check counterpart to
        resolve(), for callers deciding whether creation is needed
        (ADR-013 decision 8's "check resolve/lookup first" idempotent
        rerun protocol)."""
        ...

    def add_mapping(self, mapping: ProviderIdentityMapping) -> None:
        """Durably store an additional provider reference for an
        ALREADY-EXISTING FootCap entity (ADR-012 decision 8's allowed
        many-to-one aliasing -- e.g. a provider ID being replaced or
        corrected; empirically exercised by Task 0.5.10E/F's
        reverse-many-to-one behavioral test). This method never creates
        the target entity itself -- it must not be used for first
        creation; see CompetitionMappingCreation.create_with_mapping /
        TeamMappingCreation.create_with_mapping for that.

        Durable outcome, exactly one of:

        - mapping.provider_ref is not yet mapped, AND
          mapping.footcap_entity_id exists in the target namespace
          implied by mapping.provider_ref's correspondence (ADR-012
          decision 3): insert the mapping.
        - mapping.provider_ref is already mapped to that exact
          mapping.footcap_entity_id: idempotent success (ADR-012
          decision 9) -- nothing changes, nothing is raised.
        - mapping.provider_ref is already mapped to a DIFFERENT
          footcap_entity_id: raise ProviderMappingConflictError -- no
          silent remapping/overwrite (ADR-012 decision 10).
        - mapping.footcap_entity_id does not exist in the expected
          target namespace: raise ReferencedEntityNotFoundError
          (ADR-015 decision 8; Task 0.5.8D's transactional target-
          existence requirement).

        An unsupported provider/entity_type correspondence is never a
        concern of this method -- mapping is already a validated
        ProviderIdentityMapping by the time it is constructed, and that
        validation (ADR-012 decision 3) already happened at its own
        constructor; this contract does not re-validate it or invent a
        new error for that case."""
        ...
