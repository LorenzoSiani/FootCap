"""
Pure unit tests for the FOOTCAP_TEST_DATABASE_URL safety guard (Task
0.5.10D.2; ADR-015).

These tests exercise _validate_test_database_url() directly as a plain
Python function -- no Docker, no PostgreSQL, no FOOTCAP_TEST_DATABASE_URL
environment variable, and no psycopg connection. They are deliberately
NOT marked `db`, and must run in every ordinary pytest invocation, since
they protect a safety boundary rather than requiring live infrastructure.

`db.conftest` is importable because engine/pyproject.toml's
pythonpath = ["tests"] already puts engine/tests on sys.path (the same
mechanism engine/tests/contracts/test_schema_infrastructure.py relies on
to import `support.schema_loader`), and engine/tests/db/__init__.py makes
`db` a regular package.
"""
import pytest

from db.conftest import DatabaseSafetyError, _validate_test_database_url

CANONICAL_URL = "postgresql://postgres:postgres@localhost:5433/footcap_test"


# ==== Positive matrix: canonical safe URLs ====

@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:postgres@localhost:5433/footcap_test",
        "postgres://postgres:postgres@localhost:5433/footcap_test",
        "postgresql://postgres:postgres@127.0.0.1:5433/footcap_test",
        "postgresql://postgres:postgres@[::1]:5433/footcap_test",
    ],
    ids=["postgresql-scheme", "postgres-scheme", "ipv4", "ipv6"],
)
def test_accepts_canonical_safe_urls(url):
    assert _validate_test_database_url(url) == url


def test_accepts_the_exact_env_example_url():
    # Guards against this task silently narrowing the harness below what
    # .env.example itself documents as the intended local URL.
    assert _validate_test_database_url(CANONICAL_URL) == CANONICAL_URL


# ==== Negative matrix A: query-string bypasses ====

@pytest.mark.parametrize(
    "query",
    [
        "hostaddr=203.0.113.10",
        "host=remote.example.com",
        "dbname=production",
        "sslmode=require",
        "application_name=test",
        "foo=bar",
    ],
)
def test_rejects_any_query_parameter(query):
    url = f"{CANONICAL_URL}?{query}"
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


# ==== Negative matrix B: fragments ====

def test_rejects_fragment():
    url = f"{CANONICAL_URL}#anything"
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


# ==== Negative matrix C: remote/private/LAN/alias hosts ====

@pytest.mark.parametrize(
    "host",
    [
        "remote.example.com",
        "192.168.1.10",
        "10.0.0.5",
        "host.docker.internal",
        "localhost.example.com",
    ],
)
def test_rejects_non_local_host(host):
    url = f"postgresql://postgres:postgres@{host}:5433/footcap_test"
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


# ==== Negative matrix D: database near-matches ====

@pytest.mark.parametrize(
    "database",
    ["footcap_test_prod", "prod_footcap_test", "my_footcap_test", "footcap"],
)
def test_rejects_database_near_matches(database):
    url = f"postgresql://postgres:postgres@localhost:5433/{database}"
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


def test_rejects_root_path_with_no_database():
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url("postgresql://postgres:postgres@localhost:5433/")


# ==== Negative matrix E: bad schemes ====

@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:5433/footcap_test",
        "https://localhost:5433/footcap_test",
        "mysql://localhost:5433/footcap_test",
        "file://localhost:5433/footcap_test",
    ],
)
def test_rejects_wrong_scheme(url):
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


# ==== Negative matrix F: malformed / incomplete URLs ====

@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "localhost:5433/footcap_test",
        "postgresql://",
        "postgresql://localhost",
        "postgresql://localhost/",
        "postgresql:///footcap_test",
    ],
)
def test_rejects_malformed_urls_cleanly(url):
    # Must raise exactly DatabaseSafetyError -- never a raw ValueError,
    # AttributeError, or IndexError leaking out of the validator.
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


def test_rejects_out_of_range_port_without_leaking_value_error():
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(
            "postgresql://postgres:postgres@localhost:9999999999999/footcap_test"
        )


@pytest.mark.parametrize("port", [5432, 5434])
def test_rejects_non_default_test_port(port):
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(f"postgresql://postgres:postgres@localhost:{port}/footcap_test")


def test_rejects_missing_port():
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url("postgresql://postgres:postgres@localhost/footcap_test")


# ==== Negative matrix G: credential edge cases ====

def test_url_encoded_credentials_do_not_bypass_validation_but_canonical_form_is_accepted():
    # An @ / : embedded (URL-encoded) in the password must not confuse
    # parsing of host/path/query/fragment. Assert only that the accepted
    # URL still round-trips -- never assert on credential contents.
    url = "postgresql://postgres:p%40ss%2Fw%3Ard@localhost:5433/footcap_test"
    assert _validate_test_database_url(url) == url


def test_url_encoded_credentials_do_not_bypass_a_remote_host_rejection():
    url = "postgresql://postgres:p%40ss%2Fw%3Ard@remote.example.com:5433/footcap_test"
    with pytest.raises(DatabaseSafetyError):
        _validate_test_database_url(url)


# ==== Error-message safety ====

def test_rejection_message_does_not_echo_credentials():
    url = "postgresql://postgres:super-secret-password@remote.example.com:5433/footcap_test"
    with pytest.raises(DatabaseSafetyError) as excinfo:
        _validate_test_database_url(url)
    assert "super-secret-password" not in str(excinfo.value)
    assert url not in str(excinfo.value)


def test_rejection_message_identifies_the_problem_category():
    with pytest.raises(DatabaseSafetyError, match="host"):
        _validate_test_database_url("postgresql://postgres:postgres@remote.example.com:5433/footcap_test")
    with pytest.raises(DatabaseSafetyError, match="database name"):
        _validate_test_database_url("postgresql://postgres:postgres@localhost:5433/footcap")
    with pytest.raises(DatabaseSafetyError, match="query parameters"):
        _validate_test_database_url(f"{CANONICAL_URL}?sslmode=require")
    with pytest.raises(DatabaseSafetyError, match="fragment"):
        _validate_test_database_url(f"{CANONICAL_URL}#x")
    with pytest.raises(DatabaseSafetyError, match="scheme"):
        _validate_test_database_url("mysql://postgres:postgres@localhost:5433/footcap_test")
