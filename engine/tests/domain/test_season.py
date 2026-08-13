"""
Executable invariant test matrix for the Season value object (Task
0.5.7E; ADR-014).

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath -- it only adds "tests" (for the existing
support.schema_loader import pattern used by engine/tests/contracts/).
Without it, footcap_engine would not be importable from this file. Mirrors
engine/tests/domain/test_identity.py.
"""
import dataclasses
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from footcap_engine.domain import Season, SeasonInputError


# ==== Construction / field semantics (matrix items 1-2) ====

def test_valid_construction():
    season = Season(competition_id="competition-1", start_year=2025)
    assert season.competition_id == "competition-1"
    assert season.start_year == 2025


def test_frozen_mutation_rejected():
    season = Season(competition_id="competition-1", start_year=2025)
    with pytest.raises(dataclasses.FrozenInstanceError):
        season.start_year = 2026


# ==== Equality / hash / identity (matrix items 4-7) ====

def test_identical_seasons_compare_equal():
    a = Season(competition_id="competition-1", start_year=2025)
    b = Season(competition_id="competition-1", start_year=2025)
    assert a == b


def test_identical_seasons_have_equal_hash():
    a = Season(competition_id="competition-1", start_year=2025)
    b = Season(competition_id="competition-1", start_year=2025)
    assert hash(a) == hash(b)


def test_different_competition_id_is_unequal():
    a = Season(competition_id="competition-1", start_year=2025)
    b = Season(competition_id="competition-2", start_year=2025)
    assert a != b


def test_different_start_year_is_unequal():
    a = Season(competition_id="competition-1", start_year=2025)
    b = Season(competition_id="competition-1", start_year=2026)
    assert a != b


def test_same_start_year_under_different_competitions_is_distinct():
    a = Season(competition_id="serie-a-internal", start_year=2025)
    b = Season(competition_id="premier-league-internal", start_year=2025)
    assert a != b
    assert a.start_year == b.start_year
    assert a.competition_id != b.competition_id


# ==== competition_id validation (matrix items 8-11) ====

@pytest.mark.parametrize("bad_value", ["", "   ", 123])
def test_rejects_invalid_competition_id(bad_value):
    with pytest.raises(SeasonInputError):
        Season(competition_id=bad_value, start_year=2025)


def test_padded_competition_id_preserved_exactly():
    season = Season(competition_id=" competition-1 ", start_year=2025)
    assert season.competition_id == " competition-1 "


# ==== start_year validation (matrix items 12-19) ====

@pytest.mark.parametrize("boundary_year", [1000, 9999])
def test_accepts_boundary_start_years(boundary_year):
    season = Season(competition_id="competition-1", start_year=boundary_year)
    assert season.start_year == boundary_year


@pytest.mark.parametrize("bad_year", [999, 10000, True, False, "2025", 2025.0])
def test_rejects_invalid_start_year(bad_year):
    with pytest.raises(SeasonInputError):
        Season(competition_id="competition-1", start_year=bad_year)


# ==== Minimality (matrix items 21-25) ====

def test_no_season_id_attribute():
    season = Season(competition_id="competition-1", start_year=2025)
    assert not hasattr(season, "season_id")


def test_no_end_year_attribute():
    season = Season(competition_id="competition-1", start_year=2025)
    assert not hasattr(season, "end_year")


def test_no_label_attribute():
    season = Season(competition_id="competition-1", start_year=2025)
    assert not hasattr(season, "label")


def test_no_provider_attribute():
    season = Season(competition_id="competition-1", start_year=2025)
    assert not hasattr(season, "provider")
    assert not hasattr(season, "provider_season_value")


def test_no_temporal_or_provenance_attributes():
    season = Season(competition_id="competition-1", start_year=2025)
    for forbidden in ("event_at", "source_available_at", "prediction_cutoff", "temporal_classification", "job_run_id"):
        assert not hasattr(season, forbidden)


def test_only_two_declared_fields():
    field_names = {f.name for f in dataclasses.fields(Season)}
    assert field_names == {"competition_id", "start_year"}


# ==== Season identity (ADR-014 decision 2) ====

def test_season_identity_is_solely_competition_id_and_start_year():
    season = Season(competition_id="serie-a-internal", start_year=2025)
    assert dataclasses.astuple(season) == ("serie-a-internal", 2025)


# ==== Provider independence (no ProviderEntityRef coupling) ====

def test_season_module_has_no_provider_entity_ref_import():
    import footcap_engine.domain.season as season_module

    assert "ProviderEntityRef" not in vars(season_module)
    assert "ProviderIdentityMapping" not in vars(season_module)
