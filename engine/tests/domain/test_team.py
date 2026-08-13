"""
Executable invariant test matrix for the Team domain model (Task 0.5.9A;
ADR-013; ADR-015).

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath -- it only adds "tests" (for the existing
support.schema_loader import pattern used by engine/tests/contracts/).
Without it, footcap_engine would not be importable from this file. Mirrors
engine/tests/domain/test_season.py.
"""
import dataclasses
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from footcap_engine.domain import Competition, Team, TeamInputError


# ==== Construction / field validation (matrix items 1-23) ====

def test_valid_minimum_construction():
    team = Team(team_id="team-1", name="Inter")
    assert team.team_id == "team-1"
    assert team.name == "Inter"
    assert team.country is None
    assert team.national is None


def test_valid_full_construction():
    team = Team(team_id="team-1", name="Inter", country="Italy", national=False)
    assert team.country == "Italy"
    assert team.national is False


def test_frozen_mutation_rejected():
    team = Team(team_id="team-1", name="Inter")
    with pytest.raises(dataclasses.FrozenInstanceError):
        team.name = "Internazionale"


@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_team_id(bad_value):
    with pytest.raises(TeamInputError):
        Team(team_id=bad_value, name="Inter")


def test_padded_team_id_preserved_exactly():
    team = Team(team_id=" team-1 ", name="Inter")
    assert team.team_id == " team-1 "


@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_name(bad_value):
    with pytest.raises(TeamInputError):
        Team(team_id="team-1", name=bad_value)


def test_padded_name_preserved_exactly():
    team = Team(team_id="team-1", name=" Inter ")
    assert team.name == " Inter "


def test_country_none_accepted():
    team = Team(team_id="team-1", name="Inter", country=None)
    assert team.country is None


def test_valid_country_accepted():
    team = Team(team_id="team-1", name="Inter", country="Italy")
    assert team.country == "Italy"


@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_country(bad_value):
    with pytest.raises(TeamInputError):
        Team(team_id="team-1", name="Inter", country=bad_value)


def test_padded_country_preserved_exactly():
    team = Team(team_id="team-1", name="Inter", country=" Italy ")
    assert team.country == " Italy "


def test_national_none_accepted():
    team = Team(team_id="team-1", name="Inter", national=None)
    assert team.national is None


def test_national_true_accepted():
    team = Team(team_id="team-1", name="Inter", national=True)
    assert team.national is True


def test_national_false_accepted():
    team = Team(team_id="team-1", name="Inter", national=False)
    assert team.national is False


@pytest.mark.parametrize("bad_value", [0, 1, "true", "false"])
def test_rejects_non_bool_national(bad_value):
    with pytest.raises(TeamInputError):
        Team(team_id="team-1", name="Inter", national=bad_value)


# ==== Identity semantics (matrix items 24-31) ====

def test_same_id_same_metadata_equal():
    a = Team(team_id="t1", name="Inter")
    b = Team(team_id="t1", name="Inter")
    assert a == b


def test_same_id_different_name_still_equal():
    a = Team(team_id="t1", name="Internazionale")
    b = Team(team_id="t1", name="Inter", country="Italy")
    assert a == b


def test_same_id_different_country_still_equal():
    a = Team(team_id="t1", name="Inter", country="Italy")
    b = Team(team_id="t1", name="Inter", country=None)
    assert a == b


def test_same_id_different_national_still_equal():
    a = Team(team_id="t1", name="Inter", national=True)
    b = Team(team_id="t1", name="Inter", national=False)
    assert a == b


def test_same_id_same_hash_across_metadata_changes():
    a = Team(team_id="t1", name="Internazionale")
    b = Team(team_id="t1", name="Inter", country="Italy", national=False)
    assert hash(a) == hash(b)


def test_different_id_is_unequal():
    a = Team(team_id="t1", name="Inter")
    b = Team(team_id="t2", name="Inter")
    assert a != b


def test_same_name_different_ids_is_unequal():
    a = Team(team_id="t1", name="Inter")
    b = Team(team_id="t2", name="Inter")
    assert a != b
    assert a.name == b.name


def test_set_and_dict_behavior_uses_team_id_only():
    a = Team(team_id="t1", name="Internazionale")
    b = Team(team_id="t1", name="Inter")
    assert len({a, b}) == 1
    mapping = {a: "first"}
    mapping[b] = "second"
    assert len(mapping) == 1
    assert mapping[a] == "second"


# ==== Field boundary (matrix item 23) ====

def test_only_four_declared_fields():
    field_names = {f.name for f in dataclasses.fields(Team)}
    assert field_names == {"team_id", "name", "country", "national"}


def test_no_competition_or_season_field():
    team = Team(team_id="t1", name="Inter")
    for forbidden in ("competition_id", "season_id", "start_year"):
        assert not hasattr(team, forbidden)


# ==== Cross-model identity (Task section 24-25) ====

def test_team_never_equals_competition_with_same_id_string():
    team = Team(team_id="entity-1", name="Inter")
    competition = Competition(competition_id="entity-1", name="Serie A")
    assert team != competition
    assert not (team == competition)


def test_team_not_equal_to_unrelated_object():
    team = Team(team_id="t1", name="Inter")
    assert team != "t1"
    assert team != 42


# ==== Metadata snapshot pattern (Task section 27) ====

def test_metadata_snapshot_pattern_preserves_identity():
    old = Team(team_id="t1", name="Internazionale")
    new = Team(team_id="t1", name="Inter")
    assert old == new
    assert old.name == "Internazionale"
    assert new.name == "Inter"


# ==== Provider independence ====

def test_team_module_has_no_provider_coupling():
    import footcap_engine.domain.team as team_module

    assert "ProviderEntityRef" not in vars(team_module)
    assert "ProviderIdentityMapping" not in vars(team_module)
