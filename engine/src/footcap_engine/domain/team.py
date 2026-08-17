"""
Team domain model (ADR-013; ADR-015 decision 4).

Team identity is provider-independent and, per ADR-013 decision 4,
explicitly Competition- and Season-independent -- there is no
competition_id, season_id, or start_year field here, and none may be
added without reopening that decision. Semantic identity is team_id
alone; name, country, and national are mutable metadata that must never
establish or affect identity (ADR-013 decision 14; ADR-015 decision 4).
Provider team IDs must not appear here; they belong exclusively in
ProviderIdentityMapping.

Provider-independent by design: this module has no dependency on
ProviderEntityRef, ProviderIdentityMapping, RawObservation, or any
provider adapter. Provider-specific normalization remains the
adapter/consumer boundary, not Team's.
"""
from __future__ import annotations

from dataclasses import dataclass


class TeamInputError(ValueError):
    """Malformed or structurally invalid input to Team construction: a
    non-string/blank team_id or name, a country that is present but not
    a non-blank string, or a national value that is present but not an
    actual bool. Scoped to Team value construction only -- distinct from
    IdentityInputError, SeasonInputError, and CompetitionInputError."""


def _validate_non_blank_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TeamInputError(f"{field_name} must be a string, got {type(value)!r}")
    if value.strip() == "":
        raise TeamInputError(f"{field_name} must not be blank or whitespace-only")


def _validate_optional_non_blank_string(value: object, field_name: str) -> None:
    if value is None:
        return
    _validate_non_blank_string(value, field_name)


def _validate_optional_bool(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, bool):
        raise TeamInputError(f"{field_name} must be a bool, got {type(value)!r}")


@dataclass(frozen=True, eq=False)
class Team:
    """FootCap Team (ADR-013 decisions 3-4, 14; ADR-015 decision 4).
    Identity is exactly team_id -- name, country, and national are
    mutable metadata that must never affect equality/hash. No
    competition_id, season, provider team ID, code, founded, logo, or
    persistence-only field (ADR-013 decision 4; ADR-015 decision 4, 16)."""

    team_id: str
    name: str
    country: str | None = None
    national: bool | None = None

    def __post_init__(self) -> None:
        _validate_non_blank_string(self.team_id, "team_id")
        _validate_non_blank_string(self.name, "name")
        _validate_optional_non_blank_string(self.country, "country")
        _validate_optional_bool(self.national, "national")

    def __eq__(self, other: object) -> bool:
        if type(other) is not Team:
            return NotImplemented
        return self.team_id == other.team_id

    def __hash__(self) -> int:
        return hash(self.team_id)
