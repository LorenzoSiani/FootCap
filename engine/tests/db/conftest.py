"""
Local PostgreSQL test-infrastructure fixtures (Tasks 0.5.10D/0.5.10E;
ADR-015).

test_database_url and db_connection establish connectivity only -- they
never apply the core migration, create schema, or run any destructive
SQL; db_connection remains what test_connection.py uses. migrated_database
and migrated_db_connection (added in Task 0.5.10E, see below) are the only
fixtures in this module that mutate schema, and only ever against a URL
that has already passed the safety guard.

FOOTCAP_TEST_DATABASE_URL must be set explicitly; it is never guessed or
defaulted, so a DB test explicitly requested via `pytest -m db` fails
clearly rather than silently connecting to (or skipping past) an
unintended database. Before any connection is opened, the configured URL
is parsed and validated to target exactly the dedicated local test
database -- this guard exists so later, more destructive test
infrastructure (schema reset, migration application) can rely on it
rather than re-deriving it.

The accepted URL shape is deliberately narrow: scheme postgresql/postgres,
host localhost/127.0.0.1/::1, port 5433 (the exact port compose.yaml
publishes), database exactly footcap_test, and an EMPTY query string and
fragment. Query parameters are rejected wholesale rather than blacklisted,
because libpq connection URIs support parameters (e.g. hostaddr, host)
that can silently redirect the effective connection target even when the
URL's own host/path look local -- a blacklist of "known dangerous"
parameter names would always be one future libpq parameter behind. The
validator never hands the raw URL to psycopg merely to discover its
target; safety is decided purely from urlsplit's own structural fields
before any connection is attempted.

psycopg is imported lazily, inside db_connection (and the migration
fixtures below), rather than at module level. pytest loads every
conftest.py under testpaths unconditionally during collection -- before
marker-based deselection (`-m "not db"`) excludes anything -- so a
top-level `import psycopg` here would break every ordinary, non-DB pytest
run whenever psycopg is not installed, defeating the point of DB tests
being opt-in.

migrated_database / migrated_db_connection (Task 0.5.10E) add the first
DESTRUCTIVE operation this package performs: resetting the public schema
and applying the real core migration
(supabase/migrations/20260813224850_core_domain_persistence.sql) so its
runtime structure can actually be verified against PostgreSQL, not merely
read as text. This is safe here ONLY because both fixtures depend on
test_database_url, which has already run the full safety guard above
before either fixture's body executes -- neither fixture re-validates the
URL itself, and neither is ever called with a raw, unvalidated URL. The
migration file itself is read and executed verbatim; its SQL is never
duplicated or re-derived in Python.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

_ALLOWED_SCHEMES = frozenset({"postgresql", "postgres"})
_TEST_SAFE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_REQUIRED_PORT = 5433
_TEST_DATABASE_NAME = "footcap_test"
_CONNECT_TIMEOUT_SECONDS = 5

# The exact, already-committed, already-statically-reviewed migration file
# (Task 0.5.10B) this task proves at runtime. Deliberately not a
# glob/"discover all migrations" mechanism -- there is exactly one
# migration today, and building generic migration-ordering/discovery
# machinery here would be the "general production migration framework"
# this task is explicitly scoped not to create.
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "20260813224850_core_domain_persistence.sql"
)


class DatabaseSafetyError(RuntimeError):
    """The configured FOOTCAP_TEST_DATABASE_URL failed the local
    test-database safety guard (wrong/missing scheme, host, port, or
    database name, or a non-empty query string/fragment) and must not be
    used for any database operation. Never includes the raw URL, since it
    may contain credentials."""


def _validate_test_database_url(raw_url: str) -> str:
    """Structural validation only -- never a substring/"contains 'test'"
    check, and never a check performed by handing the URL to psycopg.
    Requires ALL of: scheme postgresql/postgres; host exactly
    localhost/127.0.0.1/::1; port exactly 5433 (the port compose.yaml
    publishes -- narrower than merely "some local port" is intentional,
    since collision-avoidance with a developer's own separately-installed
    Postgres was the whole reason 5433 was chosen over 5432 in the first
    place); database exactly footcap_test; and an EMPTY query string and
    fragment (rejected wholesale, not via a parameter blacklist -- see
    module docstring). Any unexpected parsing failure (e.g. an
    out-of-range port) is converted to DatabaseSafetyError rather than
    leaking a raw ValueError/AttributeError/IndexError."""
    try:
        parsed = urlsplit(raw_url)

        scheme = parsed.scheme
        if scheme not in _ALLOWED_SCHEMES:
            raise DatabaseSafetyError(
                f"refusing to use FOOTCAP_TEST_DATABASE_URL: scheme {scheme!r} is not one of "
                f"{sorted(_ALLOWED_SCHEMES)}"
            )

        host = parsed.hostname
        if host is None or host not in _TEST_SAFE_HOSTS:
            raise DatabaseSafetyError(
                f"refusing to use FOOTCAP_TEST_DATABASE_URL: host {host!r} is not one of "
                f"the test-safe hosts {sorted(_TEST_SAFE_HOSTS)}"
            )

        try:
            port = parsed.port
        except ValueError:
            raise DatabaseSafetyError(
                "refusing to use FOOTCAP_TEST_DATABASE_URL: port is not a valid integer"
            ) from None
        if port != _REQUIRED_PORT:
            raise DatabaseSafetyError(
                f"refusing to use FOOTCAP_TEST_DATABASE_URL: port {port!r} is not the "
                f"dedicated local test port {_REQUIRED_PORT}"
            )

        database = parsed.path.lstrip("/")
        if database != _TEST_DATABASE_NAME:
            raise DatabaseSafetyError(
                f"refusing to use FOOTCAP_TEST_DATABASE_URL: database name {database!r} is not "
                f"the dedicated test database {_TEST_DATABASE_NAME!r}"
            )

        if parsed.query:
            raise DatabaseSafetyError(
                "refusing to use FOOTCAP_TEST_DATABASE_URL: query parameters are not allowed "
                "(this harness intentionally accepts only a plain local connection URL, since "
                "libpq query parameters such as hostaddr can redirect the effective target)"
            )

        if parsed.fragment:
            raise DatabaseSafetyError(
                "refusing to use FOOTCAP_TEST_DATABASE_URL: a URL fragment is not allowed"
            )
    except DatabaseSafetyError:
        raise
    except (ValueError, AttributeError, IndexError) as exc:
        raise DatabaseSafetyError(
            f"refusing to use FOOTCAP_TEST_DATABASE_URL: the URL could not be parsed ({type(exc).__name__})"
        ) from None

    return raw_url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The validated FOOTCAP_TEST_DATABASE_URL. Fails clearly -- never
    silently skips -- if the variable is missing or fails the safety
    guard, since a DB test was explicitly requested (see the `db` marker
    registered in pyproject.toml)."""
    raw_url = os.environ.get("FOOTCAP_TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail(
            "FOOTCAP_TEST_DATABASE_URL is not set. DB tests were explicitly requested "
            "(pytest -m db) but no test database URL is configured. See .env.example.",
            pytrace=False,
        )
    try:
        return _validate_test_database_url(raw_url)
    except DatabaseSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)


def _open_connection(url: str):
    """Shared connect-with-clear-failure helper for every fixture in this
    module. `url` must already have passed _validate_test_database_url
    (i.e. come from the test_database_url fixture) -- this function
    performs no safety validation of its own."""
    import psycopg

    parsed = urlsplit(url)
    safe_target = f"{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"
    try:
        return psycopg.connect(url, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"could not connect to the local test database at {safe_target} "
            f"({type(exc).__name__}). Is the local PostgreSQL container running "
            "(see compose.yaml)?",
            pytrace=False,
        )


@pytest.fixture()
def db_connection(test_database_url: str):
    """A real psycopg connection to the validated local test database.
    Opened fresh per test and always closed at teardown. No transaction
    management, migration, or schema mutation happens here -- this
    fixture proves connectivity only and is deliberately independent of
    migrated_database, so test_connection.py never applies schema."""
    connection = _open_connection(test_database_url)
    try:
        yield connection
    finally:
        connection.close()


def _reset_and_apply_migration(url: str) -> None:
    """DESTRUCTIVE: drops and recreates the public schema, then executes
    the exact, unmodified core migration file. Callers must only ever
    pass a URL that has already passed _validate_test_database_url --
    this function performs no safety validation of its own and must never
    be exposed to a raw, unvalidated URL."""
    if not _MIGRATION_PATH.is_file():
        raise FileNotFoundError(f"expected migration file not found: {_MIGRATION_PATH}")
    migration_sql = _MIGRATION_PATH.read_text(encoding="utf-8")

    connection = _open_connection(url)
    try:
        with connection.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE")
            cur.execute("CREATE SCHEMA public")
            cur.execute(migration_sql)
        connection.commit()
    finally:
        connection.close()


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> None:
    """Session-scoped: resets the public schema and applies the real core
    migration exactly once per test session, so repeated `pytest -m db`
    invocations are repeatable regardless of what a previous run left
    behind (Task 0.5.10E Step 4/15) without depending on any Docker
    container rebuild. Depending on test_database_url in the signature is
    what makes the destructive reset safe here -- it guarantees the URL
    safety guard has already passed before this fixture's body runs."""
    _reset_and_apply_migration(test_database_url)


@pytest.fixture()
def migrated_db_connection(migrated_database: None, test_database_url: str):
    """A fresh psycopg connection opened only after the migration has
    been applied for this session. Depending on `migrated_database` as a
    fixture parameter (not merely importing it) is what guarantees pytest
    resolves the migration setup before this connection is opened.
    Rolled back (never committed) and closed at teardown so no test's
    inserted rows persist into the next test."""
    connection = _open_connection(test_database_url)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()
