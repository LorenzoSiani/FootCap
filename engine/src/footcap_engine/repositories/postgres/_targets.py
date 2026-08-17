"""Closed mapping from provider entity namespace to persisted target.

This module does not validate provider-specific correspondence. A
ProviderIdentityMapping has already done that in the domain layer. It answers
only which currently persisted FootCap relation represents a valid provider
entity namespace, using identifiers selected exclusively from this closed
internal mapping.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class _TargetRelation:
    schema: str
    table: str
    key_column: str


_PERSISTED_TARGETS = {
    "league": _TargetRelation("public", "competitions", "competition_id"),
    "team": _TargetRelation("public", "teams", "team_id"),
}


def _resolve_target(entity_type: str) -> _TargetRelation:
    """Return a closed, trusted relation description for entity_type.

    Fixture is valid provider identity vocabulary, but its FootCap Match
    target has no persisted relation yet. The explicit NotImplementedError is
    temporary until Match persistence is designed; arbitrary unknown values
    fail separately rather than becoming SQL identifiers.
    """
    if entity_type == "fixture":
        raise NotImplementedError("fixture target persistence is not implemented")
    try:
        return _PERSISTED_TARGETS[entity_type]
    except KeyError:
        raise ValueError(f"unknown persisted target entity namespace: {entity_type!r}") from None
