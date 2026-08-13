"""
Executable invariant test matrix for Provider Identity Resolution (Task
0.5.5D; ADR-012; ADR-011 decisions 1-2).

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath -- it only adds "tests" (for the existing
support.schema_loader import pattern used by engine/tests/contracts/).
Without it, footcap_engine would not be importable from this file. Mirrors
engine/tests/runs/test_provenance.py.
"""
import dataclasses
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from footcap_engine.domain import (
    IdentityInputError,
    IdentityResolver,
    ProviderEntityRef,
    ProviderIdentityMapping,
    UnresolvedProviderIdentityError,
)

LEAGUE_REF = ProviderEntityRef(provider="api-football", entity_type="league", provider_entity_id="135")
TEAM_REF = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
FIXTURE_REF = ProviderEntityRef(provider="api-football", entity_type="fixture", provider_entity_id="123456")


# ==== ProviderEntityRef (matrix items 1-17) ====

def test_valid_construction():
    ref = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    assert ref.provider == "api-football"
    assert ref.entity_type == "team"
    assert ref.provider_entity_id == "505"


def test_frozen_mutation_rejected():
    ref = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.provider_entity_id = "999"


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("provider", ""),
        ("provider", "   "),
        ("provider", 123),
        ("entity_type", ""),
        ("entity_type", "   "),
        ("entity_type", 123),
        ("provider_entity_id", ""),
        ("provider_entity_id", "   "),
        ("provider_entity_id", 123),
    ],
)
def test_rejects_invalid_field(field_name, bad_value):
    kwargs = dict(provider="api-football", entity_type="team", provider_entity_id="505")
    kwargs[field_name] = bad_value
    with pytest.raises(IdentityInputError):
        ProviderEntityRef(**kwargs)


def test_equality_for_identical_refs():
    a = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    b = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    assert a == b


def test_hash_equality_for_identical_refs():
    a = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    b = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    assert hash(a) == hash(b)


def test_provider_entity_id_no_leading_zero_normalization():
    a = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    b = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="0505")
    assert a != b
    assert a.provider_entity_id != b.provider_entity_id


def test_provider_no_case_normalization():
    a = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    b = ProviderEntityRef(provider="API-FOOTBALL", entity_type="team", provider_entity_id="505")
    assert a != b
    assert a.provider != b.provider


def test_ref_allows_structurally_unknown_provider():
    ref = ProviderEntityRef(provider="some-future-provider", entity_type="team", provider_entity_id="1")
    assert ref.provider == "some-future-provider"


def test_ref_allows_structurally_unknown_entity_type():
    ref = ProviderEntityRef(provider="api-football", entity_type="banana", provider_entity_id="1")
    assert ref.entity_type == "banana"


# ==== ProviderIdentityMapping (matrix items 18-31) ====

@pytest.mark.parametrize(
    "provider_ref",
    [LEAGUE_REF, TEAM_REF, FIXTURE_REF],
    ids=["league", "team", "fixture"],
)
def test_valid_supported_mapping(provider_ref):
    mapping = ProviderIdentityMapping(provider_ref=provider_ref, footcap_entity_id="footcap-1")
    assert mapping.provider_ref == provider_ref
    assert mapping.footcap_entity_id == "footcap-1"


def test_mapping_frozen_mutation_rejected():
    mapping = ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="footcap-1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        mapping.footcap_entity_id = "footcap-2"


def test_mapping_provider_ref_wrong_type_rejected():
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref="api-football/team/505", footcap_entity_id="footcap-1")


@pytest.mark.parametrize("bad_id", ["", "   ", 123])
def test_mapping_rejects_invalid_footcap_id(bad_id):
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id=bad_id)


def test_mapping_rejects_unsupported_entity_type():
    ref = ProviderEntityRef(provider="api-football", entity_type="banana", provider_entity_id="1")
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref=ref, footcap_entity_id="footcap-1")


def test_mapping_rejects_season():
    season_ref = ProviderEntityRef(provider="api-football", entity_type="season", provider_entity_id="2026")
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref=season_ref, footcap_entity_id="footcap-1")


def test_mapping_rejects_player():
    player_ref = ProviderEntityRef(provider="api-football", entity_type="player", provider_entity_id="1")
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref=player_ref, footcap_entity_id="footcap-1")


def test_mapping_rejects_unknown_provider():
    ref = ProviderEntityRef(provider="unknown-provider", entity_type="team", provider_entity_id="1")
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref=ref, footcap_entity_id="footcap-1")


def test_mapping_rejects_provider_case_variation():
    ref = ProviderEntityRef(provider="API-FOOTBALL", entity_type="team", provider_entity_id="505")
    with pytest.raises(IdentityInputError):
        ProviderIdentityMapping(provider_ref=ref, footcap_entity_id="footcap-1")


def test_mapping_footcap_id_stored_exactly_not_trimmed():
    mapping = ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id=" footcap-1 ")
    assert mapping.footcap_entity_id == " footcap-1 "


# ==== IdentityResolver (matrix items 32-47) ====

def test_resolver_construct_with_empty_mappings():
    resolver = IdentityResolver([])
    with pytest.raises(UnresolvedProviderIdentityError):
        resolver.resolve(TEAM_REF)


def test_resolver_resolves_known_mapping():
    resolver = IdentityResolver([ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")])
    assert resolver.resolve(TEAM_REF) == "team-internal-1"


def test_resolver_unresolved_raises():
    resolver = IdentityResolver([])
    with pytest.raises(UnresolvedProviderIdentityError):
        resolver.resolve(TEAM_REF)


def test_resolver_unresolved_error_carries_exact_ref():
    resolver = IdentityResolver([])
    with pytest.raises(UnresolvedProviderIdentityError) as excinfo:
        resolver.resolve(TEAM_REF)
    assert excinfo.value.provider_ref == TEAM_REF
    assert excinfo.value.provider_ref is TEAM_REF


@pytest.mark.parametrize("bad_input", [None, "api-football/team/505", {"provider": "api-football"}, 505])
def test_resolver_rejects_invalid_resolve_input(bad_input):
    resolver = IdentityResolver([])
    with pytest.raises(IdentityInputError):
        resolver.resolve(bad_input)


def test_resolver_accepts_exact_duplicate_mapping():
    mapping = ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")
    resolver = IdentityResolver([mapping, mapping])
    assert resolver.resolve(TEAM_REF) == "team-internal-1"


def test_resolver_rejects_forward_conflict():
    conflicting = [
        ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1"),
        ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-2"),
    ]
    with pytest.raises(IdentityInputError):
        IdentityResolver(conflicting)


def test_resolver_accepts_different_refs_to_same_footcap_id():
    other_team_ref = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="999")
    resolver = IdentityResolver(
        [
            ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1"),
            ProviderIdentityMapping(provider_ref=other_team_ref, footcap_entity_id="team-internal-1"),
        ]
    )
    assert resolver.resolve(TEAM_REF) == "team-internal-1"
    assert resolver.resolve(other_team_ref) == "team-internal-1"


def test_resolver_no_reverse_uniqueness_same_provider_and_entity_type():
    # ADR-012 decision 8: the resolver must accept two distinct
    # api-football/team references aliasing to the same FootCap team.
    ref_a = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")
    ref_b = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="999")
    resolver = IdentityResolver(
        [
            ProviderIdentityMapping(provider_ref=ref_a, footcap_entity_id="team-internal-1"),
            ProviderIdentityMapping(provider_ref=ref_b, footcap_entity_id="team-internal-1"),
        ]
    )
    assert resolver.resolve(ref_a) == "team-internal-1"
    assert resolver.resolve(ref_b) == "team-internal-1"


def test_resolver_same_id_text_distinct_across_entity_types():
    league_ref = ProviderEntityRef(provider="api-football", entity_type="league", provider_entity_id="135")
    team_ref = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="135")
    resolver = IdentityResolver(
        [
            ProviderIdentityMapping(provider_ref=league_ref, footcap_entity_id="competition-internal-1"),
            ProviderIdentityMapping(provider_ref=team_ref, footcap_entity_id="team-internal-1"),
        ]
    )
    assert resolver.resolve(league_ref) == "competition-internal-1"
    assert resolver.resolve(team_ref) == "team-internal-1"


def test_resolver_does_not_normalize_reference_strings():
    padded_ref = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="0505")
    resolver = IdentityResolver([ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")])
    assert resolver.resolve(TEAM_REF) == "team-internal-1"
    with pytest.raises(UnresolvedProviderIdentityError):
        resolver.resolve(padded_ref)


def test_resolver_preserves_exact_footcap_id_value():
    resolver = IdentityResolver(
        [ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id=" team-internal-1 ")]
    )
    assert resolver.resolve(TEAM_REF) == " team-internal-1 "


def test_resolver_input_list_mutation_after_construction_has_no_effect():
    mappings = [ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")]
    resolver = IdentityResolver(mappings)
    mappings.append(ProviderIdentityMapping(provider_ref=LEAGUE_REF, footcap_entity_id="competition-internal-1"))
    mappings.clear()
    assert resolver.resolve(TEAM_REF) == "team-internal-1"
    with pytest.raises(UnresolvedProviderIdentityError):
        resolver.resolve(LEAGUE_REF)


def test_resolver_accepts_generator_and_remains_usable():
    def _generate():
        yield ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")
        yield ProviderIdentityMapping(provider_ref=LEAGUE_REF, footcap_entity_id="competition-internal-1")

    resolver = IdentityResolver(_generate())
    assert resolver.resolve(TEAM_REF) == "team-internal-1"
    assert resolver.resolve(LEAGUE_REF) == "competition-internal-1"


def test_resolver_detects_conflict_from_generator():
    def _generate():
        yield ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")
        yield ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-2")

    with pytest.raises(IdentityInputError):
        IdentityResolver(_generate())


def test_resolver_exposes_no_public_mutation_operation():
    resolver = IdentityResolver([])
    for forbidden in ("store", "lookup", "replace", "delete", "resolve_many"):
        assert not hasattr(resolver, forbidden)


# ==== Provider / FootCap separation (ADR-012 core invariant) ====

def test_fixture_resolution_returns_independent_footcap_id_not_provider_id():
    resolver = IdentityResolver(
        [ProviderIdentityMapping(provider_ref=FIXTURE_REF, footcap_entity_id="match-internal-001")]
    )
    resolved = resolver.resolve(FIXTURE_REF)
    assert resolved == "match-internal-001"
    assert resolved != FIXTURE_REF.provider_entity_id
