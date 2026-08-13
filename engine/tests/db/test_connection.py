"""
Local PostgreSQL connectivity smoke test (Task 0.5.10D; ADR-015).

Proves only that a real connection can be opened to the dedicated local
test database and that basic queries execute. Does not create, alter, or
inspect any FootCap schema -- the core migration
(supabase/migrations/20260813224850_core_domain_persistence.sql) is not
applied by this test or by any fixture in this package. Migration runtime
verification belongs to a later task (0.5.10E).
"""
import pytest

pytestmark = pytest.mark.db


def test_select_one(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_connected_to_dedicated_test_database(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        assert cur.fetchone() == ("footcap_test",)
