"""
Season repository contract (Task 0.5.11A; ADR-014).

Contract only -- no PostgreSQL, no SQL, no connection/cursor, no Supabase
concept appears anywhere in this module.

Deliberately shaped differently from Competition/Team's contracts: Season
has no ProviderEntityRef and no ProviderIdentityMapping at all (ADR-014
decisions 9-10), so there is no atomic-creation-with-mapping protocol
here at all (contrast CompetitionMappingCreation/TeamMappingCreation).
Season's full natural key (competition_id, start_year) already IS a
complete, unambiguous identity -- there is no "alias" concept the way two
different provider Team references might secretly be the same real club
-- so creation is exposed as idempotent get_or_create on this same
repository, not a separate Case-A/B/C/D atomic-creation protocol (ADR-014
decision 15).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.season import Season


@runtime_checkable
class SeasonRepository(Protocol):
    """Durable persistence boundary for Season (ADR-014; ADR-015
    decision 5). `@runtime_checkable` here only verifies that an object
    exposes methods of these names -- it does NOT check parameter or
    return types; real conformance is a static-typing concern."""

    def get(self, competition_id: str, start_year: int) -> Season | None:
        """Return the Season for this exact (competition_id, start_year)
        natural key, or None if it does not exist. Ordinary identity
        lookup -- absence is an expected outcome, never an error."""
        ...

    def get_or_create(self, season: Season) -> Season:
        """Durable outcome, exactly one of:

        - a Season for `season`'s exact (competition_id, start_year)
          natural key already exists: idempotent success -- return the
          existing Season unchanged; mutate nothing; raise nothing
          (ADR-014 decision 15). Repeated calls with the same natural key
          never raise an already-exists error and never create a
          duplicate row -- there is no Team/Competition-style
          create-once-then-conflict shape here, because Season's full
          natural key is already a complete, unambiguous identity with
          no alias concept to protect against.
        - no Season for that natural key exists, but season.competition_id
          does not reference an existing Competition (ADR-014 decision 11:
          Competition must already be resolved before Season): raise
          ReferencedEntityNotFoundError -- an abstract translation of the
          underlying foreign-key relationship, never a PostgreSQL-
          specific exception.
        - otherwise: create the Season and return it.

        This method is authorization-NEUTRAL: it never checks whether
        this call *should* happen. That the exact Competition/provider-
        season target was explicitly authorized for ingestion/bootstrap
        (ADR-014 decision 13) is decided entirely by the caller/
        application/bootstrap layer before this operation is ever
        invoked; that authorization is deliberately not persisted, and
        this method never infers, reconstructs, or approximates it from
        the absence or presence of durable state -- an existing Season
        row means only "this key was durably recorded before", nothing
        about why.

        There is no ProviderEntityRef/ProviderIdentityMapping anywhere in
        this contract (ADR-014 decisions 9-10) -- Season has no provider
        mapping of its own. There is no season_id anywhere in this
        contract (ADR-014 decision 3) and no update/delete operation --
        Season carries no mutable metadata for an update to act on, and
        deletion lifecycle remains out of scope (ADR-015 decision 16)."""
        ...
