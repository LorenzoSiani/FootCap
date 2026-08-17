"""
Executable invariant tests for the repository-layer contracts (Task
0.5.11A; hardened by Task 0.5.11A.1 Fix 7; signature coverage completed
by Task 0.5.11A.2).

This is a contract/design-only task -- there is no PostgreSQL
implementation to test. What IS genuinely testable and tested here:

- the exact public method surface of every protocol (via introspection
  of the class body itself, not a fake's behavior);
- the exact parameter order, names, semantic types, absence of unexpected
  defaults, and return type of EVERY public method on all six protocols
  (inspect.signature() for shape/order/defaults, typing.get_type_hints()
  for the actual resolved types -- not the raw postponed-evaluation
  strings from __future__ import annotations produces, which could drift
  silently, e.g. "Competition" vs "Team", while a bare string comparison
  stayed green);
- that CompetitionRepository/TeamRepository do NOT expose
  create_with_mapping, and that the new atomic-creation protocols expose
  ONLY create_with_mapping;
- absence of forbidden generic CRUD/lifecycle method names and of any
  psycopg/PostgreSQL/Supabase/connection/cursor type in any public
  annotation;
- no async methods anywhere;
- the error taxonomy's class hierarchy, carried attributes, and that
  every remaining public repository error is actually documented/used by
  a concrete contract operation;
- ProviderMappingConflictError's corrected semantics (identical replay is
  never a conflict);
- that each Protocol's structural shape is actually satisfiable by a
  plausible minimal fake (and rejects an incomplete one) via
  @runtime_checkable isinstance() checks.

Per Task 0.5.11A.1 Fix 7, tests that only proved a fake's own tautological
behavior (rather than the contract boundary itself) have been removed --
the isinstance()-based structural-conformance tests remain, since those
genuinely test the Protocol's definition, not a fake's internals. No
concrete database behavior is tested here; no database, network, or
filesystem access anywhere in this file.

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath -- it only adds "tests". Mirrors every other
engine/tests/*/test_*.py file.
"""
import inspect
import sys
import typing
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from footcap_engine.domain import (
    Competition,
    ProviderEntityRef,
    ProviderIdentityMapping,
    Season,
    Team,
    UnresolvedProviderIdentityError as DomainUnresolvedProviderIdentityError,
)
from footcap_engine.repositories import (
    CompetitionMappingCreation,
    CompetitionRepository,
    EntityAlreadyExistsError,
    ProviderIdentityMappingRepository,
    ProviderMappingConflictError,
    ReferencedEntityNotFoundError,
    RepositoryError,
    SeasonRepository,
    TeamMappingCreation,
    TeamRepository,
    UnresolvedProviderIdentityError,
)

TEAM_REF = ProviderEntityRef(provider="api-football", entity_type="team", provider_entity_id="505")

ALL_PROTOCOLS = (
    CompetitionRepository,
    CompetitionMappingCreation,
    TeamRepository,
    TeamMappingCreation,
    SeasonRepository,
    ProviderIdentityMappingRepository,
)

FORBIDDEN_METHOD_NAMES = frozenset(
    {
        "create",
        "update",
        "delete",
        "list",
        "save",
        "remove",
        "resolve_many",
        "reverse_lookup",
        "find_by_footcap_entity_id",
    }
)

FORBIDDEN_ANNOTATION_SUBSTRINGS = ("psycopg", "postgres", "sql", "supabase", "connection", "cursor")


def _public_methods(protocol_cls) -> dict:
    """The methods actually defined in this Protocol's own class body --
    never inherited typing.Protocol machinery (_is_protocol etc, which
    are already excluded by the leading-underscore filter)."""
    return {name: value for name, value in vars(protocol_cls).items() if not name.startswith("_") and callable(value)}


# ==== Exact public method surface per protocol ====

def test_competition_repository_exposes_only_get():
    assert set(_public_methods(CompetitionRepository)) == {"get"}


def test_competition_mapping_creation_exposes_only_create_with_mapping():
    assert set(_public_methods(CompetitionMappingCreation)) == {"create_with_mapping"}


def test_team_repository_exposes_only_get():
    assert set(_public_methods(TeamRepository)) == {"get"}


def test_team_mapping_creation_exposes_only_create_with_mapping():
    assert set(_public_methods(TeamMappingCreation)) == {"create_with_mapping"}


def test_season_repository_exposes_exactly_get_and_get_or_create():
    assert set(_public_methods(SeasonRepository)) == {"get", "get_or_create"}


def test_mapping_repository_exposes_exactly_resolve_lookup_add_mapping():
    assert set(_public_methods(ProviderIdentityMappingRepository)) == {"resolve", "lookup", "add_mapping"}


def test_competition_and_team_repositories_do_not_expose_create_with_mapping():
    # The specific defect Fix 1 corrects: this method must live only on
    # the dedicated atomic-creation protocols, never on the ordinary
    # per-entity repositories.
    assert "create_with_mapping" not in _public_methods(CompetitionRepository)
    assert "create_with_mapping" not in _public_methods(TeamRepository)


# ==== Exact signatures (Task 0.5.11A.2: every public method on all six
# protocols, exact order/names/types/defaults/return) ====

def _assert_signature(fn, expected_params, expected_return) -> None:
    """Verify fn's exact parameter order, names, semantic types, and
    absence of unexpected defaults, plus its exact return type.

    expected_params is an ordered list of (name, type) tuples, `self`
    excluded. Order/names/defaults come from inspect.signature();
    semantic types come from typing.get_type_hints(), which actually
    resolves the postponed string annotations `from __future__ import
    annotations` produces in the repository modules -- comparing those
    raw strings directly (e.g. sig.parameters["x"].annotation ==
    "Competition") would only catch a literal text change, not a
    semantic drift such as Competition silently becoming Team while some
    unrelated docstring/comment kept saying "Competition"."""
    sig = inspect.signature(fn)
    param_names = [name for name in sig.parameters if name != "self"]
    assert param_names == [name for name, _ in expected_params], (
        f"{fn.__qualname__}: expected parameter order {[n for n, _ in expected_params]!r}, got {param_names!r}"
    )

    for name in param_names:
        assert sig.parameters[name].default is inspect.Parameter.empty, (
            f"{fn.__qualname__}: parameter {name!r} must not have a default argument"
        )

    hints = typing.get_type_hints(fn)
    for name, expected_type in expected_params:
        assert hints[name] == expected_type, (
            f"{fn.__qualname__}: parameter {name!r} expected type {expected_type!r}, got {hints.get(name)!r}"
        )
    assert hints["return"] == expected_return, (
        f"{fn.__qualname__}: expected return type {expected_return!r}, got {hints.get('return')!r}"
    )


def test_competition_repository_get_signature():
    _assert_signature(CompetitionRepository.get, [("competition_id", str)], Competition | None)


def test_competition_mapping_creation_create_with_mapping_signature():
    _assert_signature(
        CompetitionMappingCreation.create_with_mapping,
        [("competition", Competition), ("provider_ref", ProviderEntityRef)],
        Competition,
    )


def test_team_repository_get_signature():
    _assert_signature(TeamRepository.get, [("team_id", str)], Team | None)


def test_team_mapping_creation_create_with_mapping_signature():
    _assert_signature(
        TeamMappingCreation.create_with_mapping,
        [("team", Team), ("provider_ref", ProviderEntityRef)],
        Team,
    )


def test_season_repository_get_signature():
    _assert_signature(SeasonRepository.get, [("competition_id", str), ("start_year", int)], Season | None)


def test_season_repository_get_or_create_signature():
    _assert_signature(SeasonRepository.get_or_create, [("season", Season)], Season)


def test_mapping_repository_resolve_signature():
    _assert_signature(ProviderIdentityMappingRepository.resolve, [("provider_ref", ProviderEntityRef)], str)


def test_mapping_repository_lookup_signature():
    _assert_signature(ProviderIdentityMappingRepository.lookup, [("provider_ref", ProviderEntityRef)], str | None)


def test_mapping_repository_add_mapping_signature():
    # typing.get_type_hints() resolves a "-> None" annotation to
    # type(None) (NoneType), not the literal None object.
    _assert_signature(
        ProviderIdentityMappingRepository.add_mapping, [("mapping", ProviderIdentityMapping)], type(None)
    )


# Meta-test: confirm every public method across all six protocols was
# actually exercised above by _assert_signature, and none was
# accidentally skipped when a protocol's method set changes in the
# future -- keeps this file honest about the "every public method"
# coverage claim rather than relying on the enumeration staying in sync
# by hand.
_SIGNATURE_TESTED_METHODS = {
    (CompetitionRepository, "get"),
    (CompetitionMappingCreation, "create_with_mapping"),
    (TeamRepository, "get"),
    (TeamMappingCreation, "create_with_mapping"),
    (SeasonRepository, "get"),
    (SeasonRepository, "get_or_create"),
    (ProviderIdentityMappingRepository, "resolve"),
    (ProviderIdentityMappingRepository, "lookup"),
    (ProviderIdentityMappingRepository, "add_mapping"),
}


def test_every_public_method_on_every_protocol_has_a_signature_test():
    actual_methods = {
        (protocol_cls, name) for protocol_cls in ALL_PROTOCOLS for name in _public_methods(protocol_cls)
    }
    assert actual_methods == _SIGNATURE_TESTED_METHODS, (
        f"protocol methods without signature coverage: {actual_methods - _SIGNATURE_TESTED_METHODS!r}; "
        f"signature tests referencing methods that no longer exist: {_SIGNATURE_TESTED_METHODS - actual_methods!r}"
    )


# ==== Forbidden shapes ====

@pytest.mark.parametrize("protocol_cls", ALL_PROTOCOLS, ids=[c.__name__ for c in ALL_PROTOCOLS])
def test_no_forbidden_generic_crud_method_names(protocol_cls):
    forbidden_present = set(_public_methods(protocol_cls)) & FORBIDDEN_METHOD_NAMES
    assert not forbidden_present, f"{protocol_cls.__name__} exposes forbidden generic method(s): {forbidden_present!r}"


@pytest.mark.parametrize("protocol_cls", ALL_PROTOCOLS, ids=[c.__name__ for c in ALL_PROTOCOLS])
def test_no_async_methods(protocol_cls):
    for name, fn in _public_methods(protocol_cls).items():
        assert not inspect.iscoroutinefunction(fn), f"{protocol_cls.__name__}.{name} must not be async"


@pytest.mark.parametrize("protocol_cls", ALL_PROTOCOLS, ids=[c.__name__ for c in ALL_PROTOCOLS])
def test_no_forbidden_types_in_public_annotations(protocol_cls):
    for name, fn in _public_methods(protocol_cls).items():
        sig = inspect.signature(fn)
        annotations = [str(p.annotation) for p in sig.parameters.values()] + [str(sig.return_annotation)]
        lowered = " ".join(annotations).lower()
        for forbidden in FORBIDDEN_ANNOTATION_SUBSTRINGS:
            assert forbidden not in lowered, (
                f"{protocol_cls.__name__}.{name} annotation mentions forbidden concept {forbidden!r}: {annotations!r}"
            )


def test_no_generic_repository_base_is_used():
    # None of the six protocols subclass any shared, generic,
    # parametrized base beyond typing.Protocol itself.
    for protocol_cls in ALL_PROTOCOLS:
        bases = [b for b in protocol_cls.__bases__ if b.__name__ != "Protocol"]
        assert bases == [], f"{protocol_cls.__name__} has an unexpected non-Protocol base: {bases!r}"


# ==== Error taxonomy ====

def test_entity_already_exists_error_is_a_repository_error_and_carries_identity():
    error = EntityAlreadyExistsError("competition", "serie-a")
    assert isinstance(error, RepositoryError)
    assert error.entity_type == "competition"
    assert error.entity_id == "serie-a"


def test_referenced_entity_not_found_error_is_a_repository_error_and_carries_identity():
    error = ReferencedEntityNotFoundError("competition", "does-not-exist")
    assert isinstance(error, RepositoryError)
    assert error.entity_type == "competition"
    assert error.entity_id == "does-not-exist"


def test_provider_mapping_conflict_error_is_a_repository_error_and_carries_the_ref():
    error = ProviderMappingConflictError(TEAM_REF)
    assert isinstance(error, RepositoryError)
    assert error.provider_ref is TEAM_REF


def test_provider_mapping_conflict_error_semantics_exclude_identical_replay():
    # Fix 3: the docstring must describe this error as meaning ONLY a
    # different target -- never an identical existing mapping.
    doc = ProviderMappingConflictError.__doc__
    assert "different" in doc.lower()
    assert "idempotent" in doc.lower()
    assert "never raise" in doc.lower() or "must never raise" in doc.lower()


def test_unresolved_provider_identity_error_is_reused_not_duplicated():
    # The repository package re-exports the exact same domain-layer type
    # -- not a second, look-alike exception.
    assert UnresolvedProviderIdentityError is DomainUnresolvedProviderIdentityError


@pytest.mark.parametrize(
    "error_cls,owning_doc",
    [
        (EntityAlreadyExistsError, CompetitionMappingCreation.create_with_mapping.__doc__),
        (EntityAlreadyExistsError, TeamMappingCreation.create_with_mapping.__doc__),
        (ProviderMappingConflictError, CompetitionMappingCreation.create_with_mapping.__doc__),
        (ProviderMappingConflictError, TeamMappingCreation.create_with_mapping.__doc__),
        (ProviderMappingConflictError, ProviderIdentityMappingRepository.add_mapping.__doc__),
        (ReferencedEntityNotFoundError, SeasonRepository.get_or_create.__doc__),
        (ReferencedEntityNotFoundError, ProviderIdentityMappingRepository.add_mapping.__doc__),
    ],
    ids=[
        "EntityAlreadyExistsError-in-CompetitionMappingCreation",
        "EntityAlreadyExistsError-in-TeamMappingCreation",
        "ProviderMappingConflictError-in-CompetitionMappingCreation",
        "ProviderMappingConflictError-in-TeamMappingCreation",
        "ProviderMappingConflictError-in-add_mapping",
        "ReferencedEntityNotFoundError-in-SeasonRepository",
        "ReferencedEntityNotFoundError-in-add_mapping",
    ],
)
def test_every_repository_error_is_documented_by_a_concrete_operation(error_cls, owning_doc):
    assert error_cls.__name__ in owning_doc


# ==== Protocol structural conformance ====

class _FakeCompetitionRepository:
    def get(self, competition_id):
        return None


class _FakeCompetitionMappingCreation:
    def create_with_mapping(self, competition, provider_ref):
        return competition


class _FakeTeamRepository:
    def get(self, team_id):
        return None


class _FakeTeamMappingCreation:
    def create_with_mapping(self, team, provider_ref):
        return team


class _FakeSeasonRepository:
    def get(self, competition_id, start_year):
        return None

    def get_or_create(self, season):
        return season


class _FakeProviderIdentityMappingRepository:
    def resolve(self, provider_ref):
        raise UnresolvedProviderIdentityError(provider_ref)

    def lookup(self, provider_ref):
        return None

    def add_mapping(self, mapping):
        return None


def test_fake_competition_repository_satisfies_the_protocol():
    assert isinstance(_FakeCompetitionRepository(), CompetitionRepository)


def test_fake_competition_mapping_creation_satisfies_the_protocol():
    assert isinstance(_FakeCompetitionMappingCreation(), CompetitionMappingCreation)


def test_fake_team_repository_satisfies_the_protocol():
    assert isinstance(_FakeTeamRepository(), TeamRepository)


def test_fake_team_mapping_creation_satisfies_the_protocol():
    assert isinstance(_FakeTeamMappingCreation(), TeamMappingCreation)


def test_fake_season_repository_satisfies_the_protocol():
    assert isinstance(_FakeSeasonRepository(), SeasonRepository)


def test_fake_mapping_repository_satisfies_the_protocol():
    assert isinstance(_FakeProviderIdentityMappingRepository(), ProviderIdentityMappingRepository)


def test_competition_repository_fake_does_not_satisfy_mapping_creation_protocol():
    # A plain-read fake must not accidentally structurally satisfy the
    # atomic-creation protocol now that the two are separate.
    assert not isinstance(_FakeCompetitionRepository(), CompetitionMappingCreation)


def test_team_repository_fake_does_not_satisfy_mapping_creation_protocol():
    assert not isinstance(_FakeTeamRepository(), TeamMappingCreation)


def test_incomplete_fake_does_not_satisfy_mapping_protocol():
    class _MissingAddMapping:
        def resolve(self, provider_ref):
            raise UnresolvedProviderIdentityError(provider_ref)

        def lookup(self, provider_ref):
            return None

    assert not isinstance(_MissingAddMapping(), ProviderIdentityMappingRepository)


def test_incomplete_fake_does_not_satisfy_season_protocol():
    class _MissingGetOrCreate:
        def get(self, competition_id, start_year):
            return None

    assert not isinstance(_MissingGetOrCreate(), SeasonRepository)


# ==== Sanity: domain types referenced by these contracts remain importable/constructible ====

def test_provider_identity_mapping_still_constructible_for_add_mapping_signature():
    mapping = ProviderIdentityMapping(provider_ref=TEAM_REF, footcap_entity_id="team-internal-1")
    assert mapping.provider_ref is TEAM_REF
    assert mapping.footcap_entity_id == "team-internal-1"


def test_competition_still_constructible_for_creation_signature():
    competition = Competition(competition_id="serie-a", name="Serie A")
    assert competition.competition_id == "serie-a"


def test_season_still_constructible_for_get_or_create_signature():
    season = Season(competition_id="serie-a", start_year=2025)
    assert season.start_year == 2025
