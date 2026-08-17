"""Non-DB tests for the shared PostgreSQL repository foundation."""

import collections.abc
import importlib
import inspect
import pkgutil
import sys
import typing
from pathlib import Path

import psycopg
import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from footcap_engine.domain import Competition, Season, Team
from footcap_engine.repositories import RepositoryError, RepositoryOperationError
from footcap_engine.repositories.postgres import ConnectionFactory
from footcap_engine.repositories.postgres._errors import _raise_repository_error
from footcap_engine.repositories.postgres._rows import (
    _competition_from_row,
    _season_from_row,
    _team_from_row,
)
from footcap_engine.repositories.postgres._targets import _resolve_target


def test_connection_factory_is_a_zero_argument_callable_alias():
    assert typing.get_origin(ConnectionFactory) is collections.abc.Callable
    parameters, return_type = typing.get_args(ConnectionFactory)
    assert parameters == []
    assert return_type is psycopg.Connection


def test_repository_operation_error_is_database_neutral_and_exported():
    assert issubclass(RepositoryOperationError, RepositoryError)
    assert RepositoryOperationError.__module__ == "footcap_engine.repositories.errors"
    assert not any("psycopg" in name.lower() for name in vars(RepositoryOperationError))


def test_psycopg_error_is_translated_without_sensitive_message_leakage():
    original = psycopg.DatabaseError("password=secret SELECT * FROM private_table")

    with pytest.raises(RepositoryOperationError) as caught:
        _raise_repository_error(original)

    assert caught.value.__cause__ is original
    message = str(caught.value)
    assert "secret" not in message
    assert "SELECT" not in message
    assert "private_table" not in message


def test_repository_error_is_preserved_without_wrapping():
    original = RepositoryOperationError("already classified")

    with pytest.raises(RepositoryOperationError) as caught:
        _raise_repository_error(original)

    assert caught.value is original
    assert caught.value.__cause__ is None


def test_competition_row_maps_exact_values():
    assert _competition_from_row((" competition-1 ", " Serie A ", "Italy")) == Competition(
        " competition-1 ", " Serie A ", "Italy"
    )


def test_team_row_maps_exact_values():
    assert _team_from_row((" Team-A ", " Inter ", "Italy", False)) == Team(
        " Team-A ", " Inter ", "Italy", False
    )


def test_season_row_maps_exact_values():
    assert _season_from_row((" Competition-A ", 2025)) == Season(" Competition-A ", 2025)


@pytest.mark.parametrize(
    "mapper,row",
    [
        (_competition_from_row, ("c1", "Serie A", "Italy", "created_at")),
        (_team_from_row, ("t1", "Inter", "Italy", False, "created_at")),
        (_season_from_row, ("c1", 2025, "created_at")),
    ],
)
def test_row_mappers_reject_storage_only_extra_columns(mapper, row):
    with pytest.raises(ValueError):
        mapper(row)


def test_league_target_is_closed_competition_relation():
    target = _resolve_target("league")
    assert (target.schema, target.table, target.key_column) == (
        "public",
        "competitions",
        "competition_id",
    )


def test_team_target_is_closed_team_relation():
    target = _resolve_target("team")
    assert (target.schema, target.table, target.key_column) == ("public", "teams", "team_id")


def test_fixture_target_is_explicitly_not_persisted():
    with pytest.raises(NotImplementedError, match="fixture target persistence"):
        _resolve_target("fixture")


def test_unknown_target_namespace_fails_without_becoming_an_identifier():
    with pytest.raises(ValueError, match="unknown persisted target"):
        _resolve_target("arbitrary.caller_supplied_table")


def test_target_resolution_requires_no_provider_name():
    assert list(inspect.signature(_resolve_target).parameters) == ["entity_type"]


def test_postgres_package_has_no_unit_of_work_or_async_infrastructure():
    # Task 0.5.11E adds the first concrete PostgresCompetitionRepository/
    # PostgresTeamRepository/PostgresSeasonRepository classes, so this test
    # no longer forbids that naming shape outright (an earlier revision
    # did, back when this package intentionally provided no concrete
    # repository at all). What remains forbidden -- a generic UnitOfWork/
    # TransactionManager, or any async entry point -- is unchanged.
    package = importlib.import_module("footcap_engine.repositories.postgres")
    modules = [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}.")
    ]
    forbidden_names = {"UnitOfWork", "TransactionManager"}
    for module in [package, *modules]:
        assert forbidden_names.isdisjoint(vars(module))
        for name, value in vars(module).items():
            if inspect.isfunction(value) and value.__module__ == module.__name__:
                assert not inspect.iscoroutinefunction(value)


def test_postgres_package_does_not_import_sqlalchemy_or_supabase_client():
    package = importlib.import_module("footcap_engine.repositories.postgres")
    modules = [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}.")
    ]
    imported_module_names = {
        value.__name__
        for module in [package, *modules]
        for value in vars(module).values()
        if inspect.ismodule(value)
    }
    assert not any(name.startswith("sqlalchemy") for name in imported_module_names)
    assert not any(name.startswith("supabase") for name in imported_module_names)
