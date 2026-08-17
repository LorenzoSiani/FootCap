"""
Real PostgreSQL proof for the first concrete repositories (Task 0.5.11E;
ADR-013; ADR-014; ADR-015).

Proves PostgresCompetitionRepository.get(), PostgresTeamRepository.get(),
PostgresSeasonRepository.get(), and PostgresSeasonRepository.get_or_create()
against the real, migrated local PostgreSQL test database -- not mocked
psycopg. Reuses conftest.py's already-safety-gated `migrated_database` /
`test_database_url` fixtures and `_open_connection` helper; this file adds
no second migration runner and never TRUNCATEs.

Row setup/verification/cleanup use direct SQL via `_open_connection`
(never the repository under test itself for setup), and remove only the
exact keys each test creates, in a `finally` block, so tests remain
independent of ordering and safe to re-run against the same session-scoped
migrated database.
"""
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
    # See test_core_migration.py's identical guard: pytest imports every
    # test module at collection time, before `-m "not db"` deselects
    # anything, so this import must stay optional at module scope.
    psycopg = None

from db.conftest import _open_connection

from footcap_engine.domain import Season
from footcap_engine.repositories import ReferencedEntityNotFoundError
from footcap_engine.repositories.postgres import (
    PostgresCompetitionRepository,
    PostgresSeasonRepository,
    PostgresTeamRepository,
)

pytestmark = pytest.mark.db

_BARRIER_TIMEOUT_SECONDS = 10
_THREAD_JOIN_TIMEOUT_SECONDS = 10
_WORKER_CONNECT_TIMEOUT_SECONDS = 5


@pytest.fixture()
def connection_factory(test_database_url):
    """A ConnectionFactory backed by conftest.py's already-safety-gated
    `_open_connection`, matching exactly how a real repository is meant to
    be constructed -- one fresh connection per call, never shared."""
    return lambda: _open_connection(test_database_url)


def _get_or_create_worker(label, url, season, barrier, results):
    """One racing get_or_create() call, in its own thread, through its own
    real PostgresSeasonRepository backed by a connection_factory that
    opens a fresh connection per call -- exactly how the repository is
    meant to be used, never a shared connection across workers. Mirrors
    test_concurrency.py's worker shape: psycopg is used directly here
    (not conftest.py's `_open_connection`, whose `pytest.fail()` does not
    propagate from a background thread), and every outcome -- success or
    failure -- is captured into `results` so the main thread can assert on
    it directly rather than relying on the thread's own return value."""

    def connection_factory():
        return psycopg.connect(url, connect_timeout=_WORKER_CONNECT_TIMEOUT_SECONDS)

    try:
        repository = PostgresSeasonRepository(connection_factory)

        try:
            barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
        except threading.BrokenBarrierError:
            # Either this worker or the other one failed to reach the
            # barrier in time -- never hang indefinitely.
            results.put({"label": label, "outcome": "BROKEN_BARRIER"})
            return

        result_season = repository.get_or_create(season)
        results.put({"label": label, "outcome": "SUCCESS", "season": result_season})
    except Exception as exc:  # noqa: BLE001 -- every worker failure mode must be captured, never swallowed.
        results.put(
            {
                "label": label,
                "outcome": "UNEXPECTED_FAILURE",
                "exception_type": type(exc).__name__,
                "error": str(exc),
            }
        )


# ==== Competition.get() ====

def test_competition_get_returns_none_for_missing_id(migrated_database, connection_factory):
    repository = PostgresCompetitionRepository(connection_factory)
    assert repository.get(f"missing-{uuid.uuid4().hex}") is None


def test_competition_get_returns_existing_row(migrated_database, test_database_url, connection_factory):
    # Competition equality is ID-only (identity is competition_id alone --
    # ADR-013/ADR-015), so `==` against a freshly-constructed Competition
    # would pass even if name/country were swapped, dropped, or otherwise
    # mis-mapped. Distinctive, unmistakably-different name/country values
    # plus explicit per-field assertions are required to actually prove
    # the repository maps each column to the correct domain field.
    competition_id = f"comp-get-{uuid.uuid4().hex}"
    expected_name = "Serie A Championship"
    expected_country = "Italy"
    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute(
                "INSERT INTO competitions (competition_id, name, country) VALUES (%s, %s, %s)",
                (competition_id, expected_name, expected_country),
            )
        setup_connection.commit()

        repository = PostgresCompetitionRepository(connection_factory)
        result = repository.get(competition_id)
        assert result is not None
        assert result.competition_id == competition_id
        assert result.name == expected_name
        assert result.country == expected_country
    finally:
        with setup_connection.cursor() as cur:
            cur.execute("DELETE FROM competitions WHERE competition_id = %s", (competition_id,))
        setup_connection.commit()
        setup_connection.close()


# ==== Team.get() ====

def test_team_get_returns_none_for_missing_id(migrated_database, connection_factory):
    repository = PostgresTeamRepository(connection_factory)
    assert repository.get(f"missing-{uuid.uuid4().hex}") is None


def test_team_get_returns_existing_row(migrated_database, test_database_url, connection_factory):
    # Team equality is ID-only (identity is team_id alone -- ADR-013/
    # ADR-015), so `==` against a freshly-constructed Team would pass even
    # if name/country/national were swapped, dropped, or otherwise
    # mis-mapped. Distinctive, unmistakably-different name/country values
    # plus explicit per-field assertions (using `is` for national, so a
    # substitution to None is also caught, not only an inversion) are
    # required to actually prove the repository maps each column to the
    # correct domain field.
    team_id = f"team-get-{uuid.uuid4().hex}"
    expected_name = "Inter Milan FC"
    expected_country = "Italy"
    expected_national = False
    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute(
                "INSERT INTO teams (team_id, name, country, national) VALUES (%s, %s, %s, %s)",
                (team_id, expected_name, expected_country, expected_national),
            )
        setup_connection.commit()

        repository = PostgresTeamRepository(connection_factory)
        result = repository.get(team_id)
        assert result is not None
        assert result.team_id == team_id
        assert result.name == expected_name
        assert result.country == expected_country
        assert result.national is expected_national
    finally:
        with setup_connection.cursor() as cur:
            cur.execute("DELETE FROM teams WHERE team_id = %s", (team_id,))
        setup_connection.commit()
        setup_connection.close()


# ==== Season.get() ====

def test_season_get_returns_none_for_missing_key(migrated_database, connection_factory):
    repository = PostgresSeasonRepository(connection_factory)
    assert repository.get(f"missing-{uuid.uuid4().hex}", 2025) is None


def test_season_get_returns_existing_row(migrated_database, test_database_url, connection_factory):
    competition_id = f"comp-season-get-{uuid.uuid4().hex}"
    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", (competition_id, "Comp"))
            cur.execute(
                "INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)", (competition_id, 2025)
            )
        setup_connection.commit()

        repository = PostgresSeasonRepository(connection_factory)
        assert repository.get(competition_id, 2025) == Season(competition_id, 2025)
    finally:
        with setup_connection.cursor() as cur:
            cur.execute("DELETE FROM seasons WHERE competition_id = %s", (competition_id,))
            cur.execute("DELETE FROM competitions WHERE competition_id = %s", (competition_id,))
        setup_connection.commit()
        setup_connection.close()


# ==== Season.get_or_create() ====

def test_season_get_or_create_creates_when_absent(migrated_database, test_database_url, connection_factory):
    # Case A: no Season row exists, Competition does -- create and return it.
    competition_id = f"comp-season-create-{uuid.uuid4().hex}"
    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", (competition_id, "Comp"))
        setup_connection.commit()

        repository = PostgresSeasonRepository(connection_factory)
        created = repository.get_or_create(Season(competition_id, 2025))
        assert created == Season(competition_id, 2025)

        # Durability: verify from a fresh, independent connection.
        verify_connection = _open_connection(test_database_url)
        try:
            with verify_connection.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM seasons WHERE competition_id = %s AND start_year = %s",
                    (competition_id, 2025),
                )
                assert cur.fetchone() is not None, "created Season row is not durably visible"
        finally:
            verify_connection.close()
    finally:
        with setup_connection.cursor() as cur:
            cur.execute("DELETE FROM seasons WHERE competition_id = %s", (competition_id,))
            cur.execute("DELETE FROM competitions WHERE competition_id = %s", (competition_id,))
        setup_connection.commit()
        setup_connection.close()


def test_season_get_or_create_idempotent_when_present(migrated_database, test_database_url, connection_factory):
    # Case B: the natural key already exists -- idempotent return, no
    # duplicate row, no error, on repeated calls.
    competition_id = f"comp-season-idempotent-{uuid.uuid4().hex}"
    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", (competition_id, "Comp"))
        setup_connection.commit()

        repository = PostgresSeasonRepository(connection_factory)
        first = repository.get_or_create(Season(competition_id, 2025))
        second = repository.get_or_create(Season(competition_id, 2025))
        assert first == Season(competition_id, 2025)
        assert second == Season(competition_id, 2025)

        verify_connection = _open_connection(test_database_url)
        try:
            with verify_connection.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM seasons WHERE competition_id = %s AND start_year = %s",
                    (competition_id, 2025),
                )
                assert cur.fetchone() == (1,), "get_or_create must not create a duplicate row on replay"
        finally:
            verify_connection.close()
    finally:
        with setup_connection.cursor() as cur:
            cur.execute("DELETE FROM seasons WHERE competition_id = %s", (competition_id,))
            cur.execute("DELETE FROM competitions WHERE competition_id = %s", (competition_id,))
        setup_connection.commit()
        setup_connection.close()


def test_season_get_or_create_raises_when_competition_missing(migrated_database, test_database_url, connection_factory):
    # Case C: Competition does not exist -- ReferencedEntityNotFoundError,
    # and no Season row is left behind by the failed attempt.
    competition_id = f"comp-does-not-exist-{uuid.uuid4().hex}"
    repository = PostgresSeasonRepository(connection_factory)

    with pytest.raises(ReferencedEntityNotFoundError) as excinfo:
        repository.get_or_create(Season(competition_id, 2025))
    assert excinfo.value.entity_type == "competition"
    assert excinfo.value.entity_id == competition_id

    verify_connection = _open_connection(test_database_url)
    try:
        with verify_connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM seasons WHERE competition_id = %s AND start_year = %s",
                (competition_id, 2025),
            )
            assert cur.fetchone() is None, "no Season row must be created when the referenced Competition is missing"
    finally:
        verify_connection.close()


def test_season_get_or_create_concurrent_same_natural_key(migrated_database, test_database_url):
    # Task 0.5.11E.2 Fix 2: two independent threads, each through its own
    # real PostgresSeasonRepository/connection, call get_or_create() on the
    # exact same (competition_id, start_year) natural key, synchronized by
    # threading.Barrier(2) immediately before the racing call -- proving
    # the existing INSERT ... ON CONFLICT DO NOTHING RETURNING ... plus
    # follow-up-SELECT implementation under real READ COMMITTED contention,
    # not merely by sequential replay. No SERIALIZABLE, advisory lock,
    # SELECT FOR UPDATE, retry loop, shared connection, or repository
    # change is introduced -- this exercises the existing implementation
    # exactly as already reviewed in Task 0.5.11E.1.
    competition_id = f"comp-season-race-{uuid.uuid4().hex}"
    start_year = 2025
    season = Season(competition_id, start_year)

    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", (competition_id, "Comp"))
        setup_connection.commit()

        barrier = threading.Barrier(2)
        results: "queue.Queue[dict]" = queue.Queue()

        thread_a = threading.Thread(
            target=_get_or_create_worker,
            args=("A", test_database_url, season, barrier, results),
            name="season-get-or-create-worker-a",
        )
        thread_b = threading.Thread(
            target=_get_or_create_worker,
            args=("B", test_database_url, season, barrier, results),
            name="season-get-or-create-worker-b",
        )

        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
        thread_b.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)

        # Task 0.5.10G.2/0.5.10G.3 pattern: this liveness gate MUST stay
        # outside (before) the try/finally below. A worker still running
        # past its own bounded timeouts could still be mid-transaction --
        # deleting rows now would race that worker's own commit/rollback.
        # Give it one further bounded chance to finish; if it still hasn't,
        # fail WITHOUT attempting cleanup, since no exact-key DELETE can be
        # issued safely while a worker might still write those same keys.
        still_alive = [t for t in (thread_a, thread_b) if t.is_alive()]
        if still_alive:
            for stuck in still_alive:
                stuck.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
            still_alive = [t for t in (thread_a, thread_b) if t.is_alive()]
        if still_alive:
            pytest.fail(
                f"worker thread(s) {[t.name for t in still_alive]!r} did not finish even after an "
                "extended join -- skipping cleanup because a still-active worker could still mutate "
                "the row this test would otherwise delete",
                pytrace=False,
            )

        # From this point on, both worker threads are guaranteed finished --
        # neither can mutate seasons/competitions again. Every failure from
        # here on must still reach cleanup, so everything that can fail
        # lives inside this try, with cleanup in its finally.
        try:
            outcomes = []
            while not results.empty():
                outcomes.append(results.get_nowait())
            assert len(outcomes) == 2, f"expected exactly 2 worker results, got {outcomes!r}"

            unexpected = [o for o in outcomes if o["outcome"] != "SUCCESS"]
            assert not unexpected, f"unexpected worker outcome(s) (broken barrier/hang/psycopg failure): {unexpected!r}"

            for outcome in outcomes:
                assert outcome["season"] == season
                assert outcome["season"].competition_id == competition_id
                assert outcome["season"].start_year == start_year

            # Post-race verification from a THIRD, independent connection --
            # never inferred from the workers' own self-reported outcomes
            # alone.
            verify_connection = _open_connection(test_database_url)
            try:
                with verify_connection.cursor() as cur:
                    cur.execute(
                        "SELECT competition_id, start_year FROM seasons WHERE competition_id = %s",
                        (competition_id,),
                    )
                    rows = cur.fetchall()
                assert len(rows) == 1, f"expected exactly one durable Season row, found {rows!r}"
                assert rows[0] == (competition_id, start_year)
            finally:
                verify_connection.close()
        finally:
            # Cleanup: exact WHERE predicates only, Season first then
            # Competition, never TRUNCATE/DROP.
            with setup_connection.cursor() as cur:
                cur.execute("DELETE FROM seasons WHERE competition_id = %s", (competition_id,))
                cur.execute("DELETE FROM competitions WHERE competition_id = %s", (competition_id,))
            setup_connection.commit()
    finally:
        setup_connection.close()
