"""
Competition domain model (ADR-013; ADR-015 decision 3).

Competition is a curated FootCap domain entity, not a first-class mirror
of any provider League response -- provider league IDs must not appear
here; they belong exclusively in ProviderIdentityMapping (ADR-013
decision 13; ADR-015 decision 3). Semantic identity is competition_id
alone (ADR-015 decision 3: "name, country, type, logo, and other
metadata never establish identity"); name and country are mutable
metadata, not identity, so ordinary dataclass field-tuple equality would
be wrong here -- unlike Season, whose full frozen-dataclass tuple *is*
its identity, Competition needs eq=False plus an explicit __eq__/__hash__
keyed on competition_id only.

Provider-independent by design: this module has no dependency on
ProviderEntityRef, ProviderIdentityMapping, RawObservation, or any
provider adapter. Provider-specific normalization remains the
adapter/consumer boundary, not Competition's.
"""
from __future__ import annotations

from dataclasses import dataclass


class CompetitionInputError(ValueError):
    """Malformed or structurally invalid input to Competition
    construction: a non-string/blank competition_id or name, or a
    country that is present but not a non-blank string. Scoped to
    Competition value construction only -- distinct from
    IdentityInputError (identity-layer input) and SeasonInputError
    (Season value construction)."""


def _validate_non_blank_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise CompetitionInputError(f"{field_name} must be a string, got {type(value)!r}")
    if value.strip() == "":
        raise CompetitionInputError(f"{field_name} must not be blank or whitespace-only")


def _validate_optional_non_blank_string(value: object, field_name: str) -> None:
    if value is None:
        return
    _validate_non_blank_string(value, field_name)


@dataclass(frozen=True, eq=False)
class Competition:
    """Curated FootCap Competition (ADR-013 decision 2; ADR-015 decision
    3). Identity is exactly competition_id -- name and country are
    mutable metadata that must never affect equality/hash. No type,
    logo, provider league ID, or persistence-only field (ADR-015 decision
    3, 16)."""

    competition_id: str
    name: str
    country: str | None = None

    def __post_init__(self) -> None:
        _validate_non_blank_string(self.competition_id, "competition_id")
        _validate_non_blank_string(self.name, "name")
        _validate_optional_non_blank_string(self.country, "country")

    def __eq__(self, other: object) -> bool:
        if type(other) is not Competition:
            return NotImplemented
        return self.competition_id == other.competition_id

    def __hash__(self) -> int:
        return hash(self.competition_id)
