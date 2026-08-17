"""
Concurrent Team + first provider mapping creation race (Task 0.5.10G;
ADR-013 decision 7; ADR-015 decisions 6, 8, 11).

Proves, on real PostgreSQL 17, the exact race ADR-015 decision 11
describes: two independent transactions each provisionally create a
DIFFERENT Team, then both attempt the SAME forward provider mapping key.
Only one may durably win; the loser's mapping insert must fail on
`provider_identity_mappings_pkey`, and rolling back its whole transaction
must remove its provisional Team too -- no orphan Team may survive.

This proves ONLY that ordinary READ COMMITTED plus the mapping table's
primary key is sufficient for THIS race, on THIS schema, today. It does
NOT prove, and must not be read as proving, future repository behavior
such as idempotent identical-replay classification, an application-level
conflict exception type, target-namespace/target-existence validation, a
retry policy, or ambiguous-commit handling -- all of those remain
explicitly deferred, unimplemented, and untested here.

No repository, storage adapter, retry logic, advisory/distributed lock,
SERIALIZABLE/REPEATABLE READ isolation, trigger, or new constraint is
introduced anywhere in this file. A UniqueViolation is the expected,
observed race outcome -- it is never caught-and-retried into success.

Task 0.5.10G.2 hardened the cleanup boundary: exact-key cleanup now
covers every failure path once both worker threads are confirmed
finished (missing/extra results, cardinality assertions, durable-state
verification), not merely the happy path. The one path that still
cannot reach cleanup is a worker thread that is still alive after an
extended join -- cleaning up then would race that worker's own
still-possible INSERT/commit/rollback, so that specific case fails
loudly without touching the database instead.
"""
import queue
import threading
import uuid

import pytest

try:
    import psycopg
except ImportError:
    # Collection-time safety, mirroring test_core_migration.py: pytest
    # imports every test module during collection, before marker-based
    # deselection (`-m "not db"`) excludes anything -- an unconditional
    # `import psycopg` here would break the ordinary, non-DB pytest run
    # whenever psycopg is not installed. psycopg is only ever dereferenced
    # once a db-marked test actually runs.
    psycopg = None

from db.conftest import _open_connection

pytestmark = pytest.mark.db

_BARRIER_TIMEOUT_SECONDS = 10
_THREAD_JOIN_TIMEOUT_SECONDS = 10
_WORKER_CONNECT_TIMEOUT_SECONDS = 5


def _worker(label, team_id, provider_entity_id, url, barrier, results):
    """One racing transaction. Runs in its own thread, on its own
    connection, opened directly against `url` (the already-validated
    test_database_url string, passed down from the main test thread --
    never a raw environment read). conftest.py's `_open_connection` is
    deliberately NOT reused here: it calls pytest.fail() on a connection
    error, and pytest.fail() raised from a background thread does not
    propagate into the test's outcome -- every failure mode here must
    instead be captured into `results` so the main thread can assert on
    it directly."""
    connection = None
    try:
        connection = psycopg.connect(url, connect_timeout=_WORKER_CONNECT_TIMEOUT_SECONDS)
        cur = connection.cursor()

        cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, %s)", (team_id, f"Race Team {label}"))

        try:
            barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
        except threading.BrokenBarrierError:
            # Either this worker or the other one failed to reach the
            # barrier in time -- never hang indefinitely.
            connection.rollback()
            results.put({"label": label, "team_id": team_id, "outcome": "BROKEN_BARRIER"})
            return

        try:
            cur.execute(
                "INSERT INTO provider_identity_mappings "
                "(provider, entity_type, provider_entity_id, footcap_entity_id) VALUES (%s, %s, %s, %s)",
                ("api-football", "team", provider_entity_id, team_id),
            )
        except psycopg.errors.UniqueViolation as exc:
            constraint_name = exc.diag.constraint_name
            connection.rollback()  # discards this worker's Team insert too -- the whole transaction.
            results.put(
                {
                    "label": label,
                    "team_id": team_id,
                    "outcome": "UNIQUE_VIOLATION_ROLLED_BACK",
                    "exception_type": type(exc).__name__,
                    "constraint_name": constraint_name,
                }
            )
            return

        connection.commit()
        results.put({"label": label, "team_id": team_id, "outcome": "COMMITTED"})
    except Exception as exc:  # noqa: BLE001 -- every worker failure mode must be captured, never swallowed.
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        results.put(
            {
                "label": label,
                "team_id": team_id,
                "outcome": "UNEXPECTED_FAILURE",
                "exception_type": type(exc).__name__,
                "error": str(exc),
            }
        )
    finally:
        if connection is not None:
            connection.close()


def test_default_isolation_level_is_read_committed(migrated_db_connection):
    # Query only -- never SET/mutate a server-global or session setting.
    with migrated_db_connection.cursor() as cur:
        cur.execute("SHOW transaction_isolation")
        assert cur.fetchone()[0] == "read committed"


def test_concurrent_team_and_mapping_creation_race(migrated_database, test_database_url):
    team_id_a = f"team-a-{uuid.uuid4().hex}"
    team_id_b = f"team-b-{uuid.uuid4().hex}"
    provider_entity_id = f"provider-race-{uuid.uuid4().hex}"

    barrier = threading.Barrier(2)
    results: "queue.Queue[dict]" = queue.Queue()

    thread_a = threading.Thread(
        target=_worker,
        args=("A", team_id_a, provider_entity_id, test_database_url, barrier, results),
        name="race-worker-a",
    )
    thread_b = threading.Thread(
        target=_worker,
        args=("B", team_id_b, provider_entity_id, test_database_url, barrier, results),
        name="race-worker-b",
    )

    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
    thread_b.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)

    # Task 0.5.10G.2: this liveness gate MUST stay outside (before) the
    # try/finally below, on purpose. A worker still running past its own
    # bounded timeouts (connect + barrier + a near-instant INSERT/commit)
    # could still be mid-transaction -- deleting rows now would race that
    # worker's own INSERT/commit/rollback. Give it one further bounded
    # chance to finish through its own existing timeout machinery; if it
    # still hasn't, fail WITHOUT attempting cleanup, since no exact-key
    # DELETE can be issued safely while a worker might still write those
    # same keys. This is the only path in this test that does not reach
    # cleanup, and it is the only path where cleanup would be unsafe.
    still_alive = [t for t in (thread_a, thread_b) if t.is_alive()]
    if still_alive:
        for stuck in still_alive:
            stuck.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
        still_alive = [t for t in (thread_a, thread_b) if t.is_alive()]
    if still_alive:
        pytest.fail(
            f"worker thread(s) {[t.name for t in still_alive]!r} did not finish even after an "
            "extended join -- skipping cleanup because a still-active worker could still mutate "
            "the rows this test would otherwise delete",
            pytrace=False,
        )

    # From this point on, both worker threads are guaranteed finished --
    # neither can mutate teams/provider_identity_mappings again. Every
    # failure from here on (missing/extra results, cardinality, durable
    # verification, etc.) must still reach cleanup, so everything that can
    # fail lives inside this try, with cleanup in its finally.
    try:
        outcomes = []
        while not results.empty():
            outcomes.append(results.get_nowait())
        assert len(outcomes) == 2, f"expected exactly 2 worker results, got {outcomes!r}"

        committed = [o for o in outcomes if o["outcome"] == "COMMITTED"]
        rolled_back = [o for o in outcomes if o["outcome"] == "UNIQUE_VIOLATION_ROLLED_BACK"]
        unexpected = [o for o in outcomes if o["outcome"] not in ("COMMITTED", "UNIQUE_VIOLATION_ROLLED_BACK")]

        assert not unexpected, f"unexpected worker outcome(s) (broken barrier/hang/other failure): {unexpected!r}"
        assert len(committed) == 1, f"expected exactly one COMMITTED winner, got {outcomes!r}"
        assert len(rolled_back) == 1, f"expected exactly one rolled-back loser, got {outcomes!r}"
        assert rolled_back[0]["exception_type"] == "UniqueViolation"
        assert rolled_back[0]["constraint_name"] == "provider_identity_mappings_pkey"

        winner_team_id = committed[0]["team_id"]
        loser_team_id = rolled_back[0]["team_id"]
        assert {winner_team_id, loser_team_id} == {team_id_a, team_id_b}

        # Post-race verification from a THIRD, independent connection --
        # never inferred from the workers' own self-reported outcomes
        # alone.
        verify_connection = _open_connection(test_database_url)
        try:
            with verify_connection.cursor() as cur:
                cur.execute(
                    "SELECT team_id FROM teams WHERE team_id = ANY(%s)",
                    ([team_id_a, team_id_b],),
                )
                surviving_team_ids = {row[0] for row in cur.fetchall()}
                assert surviving_team_ids == {winner_team_id}, (
                    f"expected exactly one surviving Team ({winner_team_id!r}), found {surviving_team_ids!r}"
                )

                cur.execute(
                    "SELECT footcap_entity_id FROM provider_identity_mappings "
                    "WHERE provider = %s AND entity_type = %s AND provider_entity_id = %s",
                    ("api-football", "team", provider_entity_id),
                )
                mapping_rows = cur.fetchall()
                assert len(mapping_rows) == 1, f"expected exactly one durable mapping, found {mapping_rows!r}"
                assert mapping_rows[0][0] == winner_team_id, "durable mapping does not point at the surviving Team"

                # Explicit orphan-prevention assertion -- not merely
                # inferred from the surviving-team-count check above.
                cur.execute("SELECT 1 FROM teams WHERE team_id = %s", (loser_team_id,))
                assert cur.fetchone() is None, f"orphan Team {loser_team_id!r} survived the losing transaction's rollback"
        finally:
            verify_connection.close()
    finally:
        # Cleanup: exact WHERE predicates only, mapping first then Teams,
        # never TRUNCATE/DROP. Runs even if an assertion above failed, so
        # a failing run never leaves race data behind for the next run.
        cleanup_connection = _open_connection(test_database_url)
        try:
            with cleanup_connection.cursor() as cur:
                cur.execute(
                    "DELETE FROM provider_identity_mappings "
                    "WHERE provider = %s AND entity_type = %s AND provider_entity_id = %s",
                    ("api-football", "team", provider_entity_id),
                )
                cur.execute("DELETE FROM teams WHERE team_id = ANY(%s)", ([team_id_a, team_id_b],))
            cleanup_connection.commit()
        finally:
            cleanup_connection.close()
