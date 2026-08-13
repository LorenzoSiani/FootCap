"""
Executable invariant test matrix for the Competition domain model (Task
0.5.9A; ADR-013; ADR-015).

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

from footcap_engine.domain import Competition, CompetitionInputError, Team


# ==== Construction / field validation (matrix items 1-17) ====

def test_valid_minimum_construction():
    competition = Competition(competition_id="competition-1", name="Serie A")
    assert competition.competition_id == "competition-1"
    assert competition.name == "Serie A"
    assert competition.country is None


def test_valid_construction_with_country():
    competition = Competition(competition_id="competition-1", name="Serie A", country="Italy")
    assert competition.country == "Italy"


def test_frozen_mutation_rejected():
    competition = Competition(competition_id="competition-1", name="Serie A")
    with pytest.raises(dataclasses.FrozenInstanceError):
        competition.name = "Serie A TIM"


@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_competition_id(bad_value):
    with pytest.raises(CompetitionInputError):
        Competition(competition_id=bad_value, name="Serie A")


def test_padded_competition_id_preserved_exactly():
    competition = Competition(competition_id=" competition-1 ", name="Serie A")
    assert competition.competition_id == " competition-1 "


@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_name(bad_value):
    with pytest.raises(CompetitionInputError):
        Competition(competition_id="competition-1", name=bad_value)


def test_padded_name_preserved_exactly():
    competition = Competition(competition_id="competition-1", name=" Serie A ")
    assert competition.name == " Serie A "


def test_country_none_accepted():
    competition = Competition(competition_id="competition-1", name="Serie A", country=None)
    assert competition.country is None


def test_valid_country_accepted():
    competition = Competition(competition_id="competition-1", name="Serie A", country="Italy")
    assert competition.country == "Italy"


@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_country(bad_value):
    with pytest.raises(CompetitionInputError):
        Competition(competition_id="competition-1", name="Serie A", country=bad_value)


def test_padded_country_preserved_exactly():
    competition = Competition(competition_id="competition-1", name="Serie A", country=" Italy ")
    assert competition.country == " Italy "


# ==== Identity semantics (matrix items 18-24) ====

def test_same_id_same_metadata_equal():
    a = Competition(competition_id="c1", name="Serie A")
    b = Competition(competition_id="c1", name="Serie A")
    assert a == b


def test_same_id_different_name_still_equal():
    a = Competition(competition_id="c1", name="Serie A")
    b = Competition(competition_id="c1", name="Serie A TIM")
    assert a == b


def test_same_id_different_country_still_equal():
    a = Competition(competition_id="c1", name="Serie A", country="Italy")
    b = Competition(competition_id="c1", name="Serie A", country=None)
    assert a == b


def test_same_id_same_hash_despite_metadata_differences():
    a = Competition(competition_id="c1", name="Serie A")
    b = Competition(competition_id="c1", name="Serie A TIM", country="Italy")
    assert hash(a) == hash(b)


def test_different_id_is_unequal():
    a = Competition(competition_id="c1", name="Serie A")
    b = Competition(competition_id="c2", name="Serie A")
    assert a != b


def test_same_name_different_ids_is_unequal():
    a = Competition(competition_id="c1", name="Serie A")
    b = Competition(competition_id="c2", name="Serie A")
    assert a != b
    assert a.name == b.name


def test_set_and_dict_key_behavior_respects_id_identity():
    a = Competition(competition_id="c1", name="Serie A")
    b = Competition(competition_id="c1", name="Serie A TIM")
    assert len({a, b}) == 1
    mapping = {a: "first"}
    mapping[b] = "second"
    assert len(mapping) == 1
    assert mapping[a] == "second"


# ==== Field boundary (matrix item 20) ====

def test_only_three_declared_fields():
    field_names = {f.name for f in dataclasses.fields(Competition)}
    assert field_names == {"competition_id", "name", "country"}


# ==== Cross-model identity (Task section 24-25) ====

def test_competition_never_equals_team_with_same_id_string():
    competition = Competition(competition_id="entity-1", name="Serie A")
    team = Team(team_id="entity-1", name="Some Team")
    assert competition != team
    assert not (competition == team)


def test_competition_not_equal_to_unrelated_object():
    competition = Competition(competition_id="c1", name="Serie A")
    assert competition != "c1"
    assert competition != 42


# ==== Metadata snapshot pattern (Task section 27) ====

def test_metadata_snapshot_pattern_preserves_identity():
    old = Competition(competition_id="c1", name="Serie A")
    new = Competition(competition_id="c1", name="Serie A TIM")
    assert old == new
    assert old.name == "Serie A"
    assert new.name == "Serie A TIM"


# ==== Provider independence ====

def test_competition_module_has_no_provider_coupling():
    import footcap_engine.domain.competition as competition_module

    assert "ProviderEntityRef" not in vars(competition_module)
    assert "ProviderIdentityMapping" not in vars(competition_module)
