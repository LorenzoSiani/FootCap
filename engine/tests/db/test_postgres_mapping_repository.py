"""Real PostgreSQL tests for PostgresProviderIdentityMappingRepository."""
import queue
import sys
import threading
import uuid
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    import psycopg
except ImportError:
    psycopg = None

from db.conftest import _open_connection
from footcap_engine.domain import ProviderEntityRef, ProviderIdentityMapping, UnresolvedProviderIdentityError
from footcap_engine.repositories import (
    ProviderMappingConflictError,
    ReferencedEntityNotFoundError,
    RepositoryOperationError,
)
from footcap_engine.repositories.mapping import ProviderIdentityMappingRepository
from footcap_engine.repositories.postgres import PostgresProviderIdentityMappingRepository

pytestmark = pytest.mark.db

_BARRIER_TIMEOUT = 10
_JOIN_TIMEOUT = 10
_CONNECT_TIMEOUT = 5


def _ref(entity_type="team", provider_entity_id=None, provider="api-football"):
    return ProviderEntityRef(provider, entity_type, provider_entity_id or uuid.uuid4().hex)


def _mapping(ref, target_id):
    return ProviderIdentityMapping(ref, target_id)


@pytest.fixture()
def connection_factory(test_database_url):
    return lambda: _open_connection(test_database_url)


@pytest.fixture()
def repository(connection_factory):
    result = PostgresProviderIdentityMappingRepository(connection_factory)
    assert isinstance(result, ProviderIdentityMappingRepository)
    return result


def _insert_target(connection, entity_type, target_id):
    table, key = ("competitions", "competition_id") if entity_type == "league" else ("teams", "team_id")
    with connection.cursor() as cur:
        cur.execute(f"INSERT INTO {table} ({key}, name) VALUES (%s, %s)", (target_id, "Mapping Target"))
    connection.commit()


def _cleanup(url, refs, competition_ids=(), team_ids=()):
    connection = _open_connection(url)
    try:
        with connection.cursor() as cur:
            for ref in refs:
                cur.execute(
                    "DELETE FROM provider_identity_mappings WHERE provider=%s AND entity_type=%s AND provider_entity_id=%s",
                    (ref.provider, ref.entity_type, ref.provider_entity_id),
                )
            for target_id in team_ids:
                cur.execute("DELETE FROM teams WHERE team_id=%s", (target_id,))
            for target_id in competition_ids:
                cur.execute("DELETE FROM competitions WHERE competition_id=%s", (target_id,))
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize("entity_type", ["league", "team"])
def test_resolve_and_lookup_existing(migrated_database, test_database_url, repository, entity_type):
    ref = _ref(entity_type)
    target_id = f"target-{uuid.uuid4().hex}"
    setup = _open_connection(test_database_url)
    try:
        _insert_target(setup, entity_type, target_id)
        repository.add_mapping(_mapping(ref, target_id))
        assert repository.resolve(ref) == target_id
        assert repository.lookup(ref) == target_id
    finally:
        setup.close()
        _cleanup(test_database_url, [ref], [target_id] if entity_type == "league" else (), [target_id] if entity_type == "team" else ())


def test_missing_lookup_and_resolve(migrated_database, repository):
    ref = _ref()
    assert repository.lookup(ref) is None
    with pytest.raises(UnresolvedProviderIdentityError) as excinfo:
        repository.resolve(ref)
    assert excinfo.value.provider_ref is ref


def test_exact_identity_and_leading_zero_semantics(migrated_database, test_database_url, repository):
    target_ids = [f"team-{uuid.uuid4().hex}" for _ in range(3)]
    refs = [_ref(provider_entity_id="505"), _ref(provider_entity_id="0505"), _ref(provider_entity_id=" 505 ")]
    setup = _open_connection(test_database_url)
    try:
        for target_id in target_ids:
            _insert_target(setup, "team", target_id)
        for ref, target_id in zip(refs, target_ids, strict=True):
            repository.add_mapping(_mapping(ref, target_id))
        assert [repository.resolve(ref) for ref in refs] == target_ids
        assert repository.lookup(ProviderEntityRef("API-FOOTBALL", "team", "505")) is None
    finally:
        setup.close()
        _cleanup(test_database_url, refs, team_ids=target_ids)


@pytest.mark.parametrize("entity_type", ["league", "team"])
def test_add_replay_conflict_and_reverse_aliases(migrated_database, test_database_url, repository, entity_type):
    target_a, target_b = f"a-{uuid.uuid4().hex}", f"b-{uuid.uuid4().hex}"
    ref, alias = _ref(entity_type), _ref(entity_type)
    setup = _open_connection(test_database_url)
    try:
        _insert_target(setup, entity_type, target_a)
        _insert_target(setup, entity_type, target_b)
        repository.add_mapping(_mapping(ref, target_a))
        repository.add_mapping(_mapping(ref, target_a))
        repository.add_mapping(_mapping(alias, target_a))
        with pytest.raises(ProviderMappingConflictError) as excinfo:
            repository.add_mapping(_mapping(ref, target_b))
        assert excinfo.value.provider_ref == ref
        assert repository.resolve(ref) == target_a
        with setup.cursor() as cur:
            cur.execute("SELECT count(*) FROM provider_identity_mappings WHERE provider=%s AND entity_type=%s AND provider_entity_id=%s", (ref.provider, ref.entity_type, ref.provider_entity_id))
            assert cur.fetchone() == (1,)
            cur.execute("SELECT count(*) FROM provider_identity_mappings WHERE footcap_entity_id=%s", (target_a,))
            assert cur.fetchone() == (2,)
    finally:
        setup.close()
        ids = [target_a, target_b]
        _cleanup(test_database_url, [ref, alias], ids if entity_type == "league" else (), ids if entity_type == "team" else ())


@pytest.mark.parametrize("entity_type,semantic_name", [("league", "competition"), ("team", "team")])
def test_missing_target_and_precedence(migrated_database, test_database_url, repository, entity_type, semantic_name):
    ref = _ref(entity_type)
    existing = f"existing-{uuid.uuid4().hex}"
    missing = f"missing-{uuid.uuid4().hex}"
    setup = _open_connection(test_database_url)
    try:
        _insert_target(setup, entity_type, existing)
        repository.add_mapping(_mapping(ref, existing))
        with pytest.raises(ReferencedEntityNotFoundError) as excinfo:
            repository.add_mapping(_mapping(ref, missing))
        assert (excinfo.value.entity_type, excinfo.value.entity_id) == (semantic_name, missing)
        assert repository.resolve(ref) == existing
    finally:
        setup.close()
        _cleanup(test_database_url, [ref], [existing] if entity_type == "league" else (), [existing] if entity_type == "team" else ())


def test_missing_target_writes_no_mapping(migrated_database, repository):
    ref = _ref("team")
    with pytest.raises(ReferencedEntityNotFoundError):
        repository.add_mapping(_mapping(ref, f"missing-{uuid.uuid4().hex}"))
    assert repository.lookup(ref) is None


def test_fixture_fails_before_connection_or_write():
    called = False
    def factory():
        nonlocal called
        called = True
        raise AssertionError("connection must not be opened")
    repository = PostgresProviderIdentityMappingRepository(factory)
    with pytest.raises(NotImplementedError, match="fixture target persistence"):
        repository.add_mapping(_mapping(_ref("fixture"), "match-id"))
    assert called is False


def _race_worker(label, url, mapping, barrier, results):
    def factory():
        return psycopg.connect(url, connect_timeout=_CONNECT_TIMEOUT)
    try:
        repository = PostgresProviderIdentityMappingRepository(factory)
        barrier.wait(timeout=_BARRIER_TIMEOUT)
        repository.add_mapping(mapping)
        results.put((label, "SUCCESS", mapping.footcap_entity_id))
    except ProviderMappingConflictError:
        results.put((label, "CONFLICT", mapping.footcap_entity_id))
    except Exception as exc:
        results.put((label, "UNEXPECTED", type(exc).__name__))


@pytest.mark.parametrize("same_target", [False, True], ids=["different-targets", "same-target"])
def test_concurrent_add_mapping(migrated_database, test_database_url, same_target):
    ref = _ref("team")
    target_a = f"race-a-{uuid.uuid4().hex}"
    target_b = target_a if same_target else f"race-b-{uuid.uuid4().hex}"
    target_ids = list(dict.fromkeys([target_a, target_b]))
    setup = _open_connection(test_database_url)
    try:
        for target_id in target_ids:
            _insert_target(setup, "team", target_id)
        barrier = threading.Barrier(2)
        results = queue.Queue()
        threads = [
            threading.Thread(target=_race_worker, args=("A", test_database_url, _mapping(ref, target_a), barrier, results)),
            threading.Thread(target=_race_worker, args=("B", test_database_url, _mapping(ref, target_b), barrier, results)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=_JOIN_TIMEOUT)
        alive = [thread for thread in threads if thread.is_alive()]
        if alive:
            for thread in alive:
                thread.join(timeout=_JOIN_TIMEOUT)
            alive = [thread for thread in threads if thread.is_alive()]
        if alive:
            pytest.fail("mapping race worker did not terminate; cleanup skipped", pytrace=False)
        try:
            outcomes = [results.get_nowait() for _ in range(results.qsize())]
            assert len(outcomes) == 2
            expected = ["SUCCESS", "SUCCESS"] if same_target else ["CONFLICT", "SUCCESS"]
            assert sorted(item[1] for item in outcomes) == expected
            verify = _open_connection(test_database_url)
            try:
                with verify.cursor() as cur:
                    cur.execute("SELECT footcap_entity_id FROM provider_identity_mappings WHERE provider=%s AND entity_type=%s AND provider_entity_id=%s", (ref.provider, ref.entity_type, ref.provider_entity_id))
                    rows = cur.fetchall()
                assert len(rows) == 1
                winners = [item[2] for item in outcomes if item[1] == "SUCCESS"]
                assert rows[0][0] in winners
            finally:
                verify.close()
        finally:
            _cleanup(test_database_url, [ref], team_ids=target_ids)
    finally:
        setup.close()


class _FailingCursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, *args): raise psycopg.OperationalError("dsn=secret SELECT private")


class _FailingConnection:
    def cursor(self): return _FailingCursor()
    def rollback(self): pass
    def close(self): pass


def test_unexpected_psycopg_error_is_translated():
    repository = PostgresProviderIdentityMappingRepository(lambda: _FailingConnection())
    with pytest.raises(RepositoryOperationError) as excinfo:
        repository.lookup(_ref())
    assert "secret" not in str(excinfo.value)
