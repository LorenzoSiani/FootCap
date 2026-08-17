"""
Provider Identity Resolution (ADR-012; ADR-011 decisions 1-2; ADR-009
decision 11).

Phase 0 scope is the semantic identity layer only: a Python-internal
reference to a provider's own entity identifier (ProviderEntityRef), an
explicit provider-to-FootCap correspondence (ProviderIdentityMapping),
and a strict, read-only resolver constructed from an explicit,
already-known set of mappings (IdentityResolver). A provider-assigned ID
is never a FootCap domain ID (ADR-011 decision 2; ADR-012 decisions 1,
7-8).

Out of Phase 0 scope, deliberately: persistence, a repository
abstraction, mutable mapping storage, entity creation, FootCap ID
generation, mapping bootstrap, normalization, and season resolution
(ADR-012 Scope / Deferrals). No database, network, or filesystem access.
No global mutable state.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Phase 0 supported provider/entity_type correspondences (ADR-012
# decision 3). A structurally valid ProviderEntityRef is not
# automatically a valid semantic mapping -- only these exact pairs are.
# "season" (ADR-012 decision 4) and "player" (ADR-012 decision 3, last
# paragraph) are deliberately absent.
_SUPPORTED_CORRESPONDENCE: dict[tuple[str, str], str] = {
    ("api-football", "league"): "competition",
    ("api-football", "team"): "team",
    ("api-football", "fixture"): "match",
}


class IdentityInputError(ValueError):
    """Malformed or structurally invalid input to the identity layer:
    ProviderEntityRef/ProviderIdentityMapping construction with a wrong
    type or a blank field, an unsupported provider/entity_type
    correspondence, a forward-uniqueness conflict detected while
    constructing an IdentityResolver, or resolve() called with something
    other than a ProviderEntityRef. Never raised merely because a
    reference has no mapped FootCap identity -- see
    UnresolvedProviderIdentityError."""


class UnresolvedProviderIdentityError(LookupError):
    """Raised when resolving provider_ref finds no mapped FootCap entity
    identity (ADR-012 decision 11; ADR-011 decision 4) -- by
    IdentityResolver.resolve() (in-memory) and, identically, by any
    ProviderIdentityMappingRepository.resolve() implementation (durable
    storage; Task 0.5.11A). Carries the exact original ProviderEntityRef
    -- the caller must never receive a fabricated or substituted FootCap
    ID."""

    def __init__(self, provider_ref: "ProviderEntityRef") -> None:
        super().__init__(f"no FootCap identity mapping for {provider_ref!r}")
        self.provider_ref = provider_ref


def _validate_non_blank_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise IdentityInputError(f"{field_name} must be a string, got {type(value)!r}")
    if value.strip() == "":
        raise IdentityInputError(f"{field_name} must not be blank or whitespace-only")


@dataclass(frozen=True)
class ProviderEntityRef:
    """Python-internal reference to a provider's own entity identifier
    (ADR-011 decision 1; ADR-012 decision 1). provider and entity_type
    remain an open, non-blank-string vocabulary -- constructing a
    structurally valid ProviderEntityRef never implies a supported
    semantic mapping exists for it (ADR-012 decision 2).

    Validation only detects blank/whitespace-only input; it never
    normalizes the stored values. There is no trimming, case-folding, or
    numeric parsing, so "505" != "0505" and "api-football" !=
    "API-FOOTBALL" (ADR-012 decision 1)."""

    provider: str
    entity_type: str
    provider_entity_id: str

    def __post_init__(self) -> None:
        _validate_non_blank_string(self.provider, "provider")
        _validate_non_blank_string(self.entity_type, "entity_type")
        _validate_non_blank_string(self.provider_entity_id, "provider_entity_id")


def _target_namespace(provider_ref: ProviderEntityRef) -> str:
    """Private Phase 0 correspondence lookup (ADR-012 decision 3, 13).
    Raises IdentityInputError for any (provider, entity_type) pair this
    Phase does not support -- including a structurally valid "season" or
    "player" ProviderEntityRef."""
    key = (provider_ref.provider, provider_ref.entity_type)
    try:
        return _SUPPORTED_CORRESPONDENCE[key]
    except KeyError:
        raise IdentityInputError(
            f"unsupported provider/entity_type correspondence: {key!r}; "
            f"supported correspondences are {sorted(_SUPPORTED_CORRESPONDENCE)}"
        ) from None


@dataclass(frozen=True)
class ProviderIdentityMapping:
    """A single provider reference resolved to a FootCap entity identity
    (ADR-012 decision 6). No footcap_entity_type field -- the target
    FootCap namespace is always derived from provider_ref's validated
    provider/entity_type correspondence, never stored redundantly.

    footcap_entity_id is opaque and stored exactly as supplied; it is
    never trimmed, parsed, or otherwise normalized (ADR-012 decision 5)."""

    provider_ref: ProviderEntityRef
    footcap_entity_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider_ref, ProviderEntityRef):
            raise IdentityInputError(
                f"provider_ref must be a ProviderEntityRef, got {type(self.provider_ref)!r}"
            )
        _validate_non_blank_string(self.footcap_entity_id, "footcap_entity_id")
        # Rejects unsupported correspondences (e.g. season, player, an
        # unknown provider, or case-variant provider names) at
        # construction time -- ADR-012 decision 2.
        _target_namespace(self.provider_ref)


class IdentityResolver:
    """Strict, read-only resolver from ProviderEntityRef to FootCap
    entity identity, built once from an explicit, already-known set of
    mappings (ADR-012 decisions 7-8, 11). Resolution-only: it never
    creates entities, generates FootCap IDs, or persists anything.

    Forward uniqueness is enforced at construction: one ProviderEntityRef
    must resolve to at most one FootCap entity identity. Supplying the
    exact same mapping more than once is idempotent; supplying the same
    provider_ref with two different footcap_entity_id values is a
    conflict and construction fails.

    Reverse cardinality is deliberately unconstrained (ADR-012 decision
    8): distinct ProviderEntityRefs -- including two references for the
    same provider and entity_type -- may resolve to the same FootCap
    entity identity."""

    def __init__(self, mappings: Iterable[ProviderIdentityMapping]) -> None:
        index: dict[ProviderEntityRef, str] = {}
        for mapping in mappings:
            if not isinstance(mapping, ProviderIdentityMapping):
                raise IdentityInputError(
                    f"mappings must contain only ProviderIdentityMapping, got {type(mapping)!r}"
                )
            ref = mapping.provider_ref
            if ref in index and index[ref] != mapping.footcap_entity_id:
                raise IdentityInputError(
                    f"conflicting FootCap identity for {ref!r}: "
                    f"{index[ref]!r} != {mapping.footcap_entity_id!r}"
                )
            index[ref] = mapping.footcap_entity_id
        self._index = index

    def resolve(self, provider_ref: ProviderEntityRef) -> str:
        """Return the mapped FootCap entity identity for provider_ref, or
        raise UnresolvedProviderIdentityError carrying the exact original
        provider_ref if no mapping exists. Never returns None."""
        if not isinstance(provider_ref, ProviderEntityRef):
            raise IdentityInputError(
                f"resolve() requires a ProviderEntityRef, got {type(provider_ref)!r}"
            )
        try:
            return self._index[provider_ref]
        except KeyError:
            raise UnresolvedProviderIdentityError(provider_ref) from None
