"""
Season value object (ADR-014).

Season is a Competition-scoped immutable domain value, not a first-class
entity -- Phase 0 introduces no opaque season_id (ADR-014 decision 3).
Its Phase 0 semantic identity is exactly (competition_id, start_year)
(ADR-014 decision 2), which the frozen dataclass's own equality/hash
already represent without a custom __eq__/__hash__.

Provider-independent by design: this module has no dependency on
ProviderEntityRef, ProviderIdentityMapping, RawObservation, or any
provider adapter (ADR-014 decisions 9-10, 16). Provider-specific season
normalization -- e.g. converting API-Football's season integer to
start_year -- remains the caller/adapter's responsibility, not Season's.

Resolution (resolve_season), persistence, bootstrap, and creation
authorization are explicitly out of scope for this module (ADR-014
decisions 12-13, 24) -- this is the value object only.
"""
from __future__ import annotations

from dataclasses import dataclass

_MIN_START_YEAR = 1000
_MAX_START_YEAR = 9999


class SeasonInputError(ValueError):
    """Malformed or structurally invalid input to Season construction: a
    non-string/blank competition_id, or a start_year that is not a
    non-bool int in [1000, 9999] (ADR-014 decision 6). Scoped to Season
    value construction only -- distinct from IdentityInputError, whose
    documented scope is ProviderEntityRef/ProviderIdentityMapping/
    IdentityResolver input, not Season."""


def _validate_competition_id(value: object) -> None:
    if not isinstance(value, str):
        raise SeasonInputError(f"competition_id must be a string, got {type(value)!r}")
    if value.strip() == "":
        raise SeasonInputError("competition_id must not be blank or whitespace-only")


def _validate_start_year(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SeasonInputError(f"start_year must be an int, got {type(value)!r}")
    if not (_MIN_START_YEAR <= value <= _MAX_START_YEAR):
        raise SeasonInputError(
            f"start_year must be a four-digit year ({_MIN_START_YEAR}-{_MAX_START_YEAR}), got {value!r}"
        )


@dataclass(frozen=True)
class Season:
    """Competition-scoped immutable Season value (ADR-014 decisions 1-2,
    5). Identity is exactly (competition_id, start_year) -- there is no
    season_id, end_year, start_date, end_date, label, provider, or
    provenance field (ADR-014 decisions 3, 7-8, 16)."""

    competition_id: str
    start_year: int

    def __post_init__(self) -> None:
        _validate_competition_id(self.competition_id)
        _validate_start_year(self.start_year)
