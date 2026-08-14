"""
First real PostgreSQL runtime validation of the core domain migration
(Task 0.5.10E; ADR-015).

Proves, against a real disposable PostgreSQL 17 instance, that
supabase/migrations/20260813224850_core_domain_persistence.sql actually
executes and that the resulting schema matches the migration file and
ADR-015 exactly: table existence, column contract, primary keys, unique
constraints, foreign keys, CHECK constraints, and real constraint
enforcement (via INSERT attempts inside transactions that are always
rolled back, never committed -- see migrated_db_connection in conftest.py).

Everything here is read from PostgreSQL's own catalogs
(information_schema), never from the Python domain models or a
hand-copied schema description -- the migration file remains the sole
source of truth, and this file only encodes the *expected* structure
independently derived from reading that file and ADR-015, to compare
against what PostgreSQL actually reports.

No repository, storage adapter, or application persistence code is
introduced here.

Task 0.5.10F adds two coverage-gap closures identified by the 0.5.10E.1
adversarial review: a direct Team duplicate-primary-key behavioral test,
and an entity + first provider mapping atomicity/orphan-prevention test
(ADR-015 decisions 8/10; ADR-013 decision 7). The atomicity test needs a
transaction that genuinely commits (to prove the success case is durable)
and independent connections to verify state from outside that
transaction -- migrated_db_connection's own always-rollback design is
deliberately unsuitable for that, so those two tests instead reuse
conftest.py's already-safety-gated `_open_connection` helper directly
against `test_database_url`, and clean up (by exact known key, never
TRUNCATE/DROP) whatever they durably commit.
"""
import uuid

import pytest

try:
    import psycopg
except ImportError:
    # Collection-time safety: pytest imports every test module during
    # collection, before marker-based deselection (`-m "not db"`) excludes
    # anything -- an unconditional `import psycopg` here would break the
    # ordinary, non-DB pytest run whenever psycopg is not installed, the
    # same hazard conftest.py's own lazy-import discipline exists to
    # avoid. psycopg is only ever dereferenced inside a running db-marked
    # test, by which point it must already be installed for the test to
    # do anything useful at all.
    psycopg = None

from db.conftest import _open_connection

pytestmark = pytest.mark.db

EXPECTED_TABLES = frozenset({"competitions", "teams", "seasons", "provider_identity_mappings"})

# (column_name, data_type, is_nullable, has_default) -- derived directly
# from the migration file, ordinal order.
EXPECTED_COLUMNS = {
    "competitions": [
        ("competition_id", "text", False, False),
        ("name", "text", False, False),
        ("country", "text", True, False),
        ("created_at", "timestamp with time zone", False, True),
        ("updated_at", "timestamp with time zone", False, True),
    ],
    "teams": [
        ("team_id", "text", False, False),
        ("name", "text", False, False),
        ("country", "text", True, False),
        ("national", "boolean", True, False),
        ("created_at", "timestamp with time zone", False, True),
        ("updated_at", "timestamp with time zone", False, True),
    ],
    "seasons": [
        ("competition_id", "text", False, False),
        ("start_year", "integer", False, False),
        ("created_at", "timestamp with time zone", False, True),
    ],
    "provider_identity_mappings": [
        ("provider", "text", False, False),
        ("entity_type", "text", False, False),
        ("provider_entity_id", "text", False, False),
        ("footcap_entity_id", "text", False, False),
        ("created_at", "timestamp with time zone", False, True),
    ],
}

EXPECTED_PRIMARY_KEYS = {
    "competitions": ("competitions_pkey", ["competition_id"]),
    "teams": ("teams_pkey", ["team_id"]),
    "seasons": ("seasons_pkey", ["competition_id", "start_year"]),
    "provider_identity_mappings": (
        "provider_identity_mappings_pkey",
        ["provider", "entity_type", "provider_entity_id"],
    ),
}

EXPECTED_CHECK_CONSTRAINTS = {
    "competitions": {
        "competitions_competition_id_nonblank",
        "competitions_name_nonblank",
        "competitions_country_nonblank",
    },
    "teams": {
        "teams_team_id_nonblank",
        "teams_name_nonblank",
        "teams_country_nonblank",
    },
    "seasons": {"seasons_start_year_range"},
    "provider_identity_mappings": {
        "provider_identity_mappings_provider_nonblank",
        "provider_identity_mappings_entity_type_nonblank",
        "provider_identity_mappings_provider_entity_id_nonblank",
        "provider_identity_mappings_footcap_entity_id_nonblank",
    },
}


# ==== Step 5: migration actually applies ====

def test_migration_applies_successfully(migrated_database, migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_migration_target_is_the_dedicated_local_test_database(migrated_db_connection):
    # Step 13: prove the *live connection*, not merely the configured URL
    # string, is the isolated local test database.
    info = migrated_db_connection.info
    assert info.host in {"localhost", "127.0.0.1", "::1"}
    assert info.port == 5433
    assert info.dbname == "footcap_test"


# ==== Step 6: table existence ====

def test_expected_tables_exist_and_no_unexpected_table_is_created(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        actual = {row[0] for row in cur.fetchall()}
    assert actual == EXPECTED_TABLES


# ==== Step 7: column contract ====

@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_column_contract(migrated_db_connection, table):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position",
            (table,),
        )
        rows = cur.fetchall()
    actual = [(name, data_type, is_nullable == "YES", default is not None) for name, data_type, is_nullable, default in rows]
    assert actual == EXPECTED_COLUMNS[table]


# ==== Step 8: primary keys ====

@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_primary_key(migrated_db_connection, table):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "SELECT tc.constraint_name, kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "WHERE tc.table_schema = 'public' AND tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY' "
            "ORDER BY kcu.ordinal_position",
            (table,),
        )
        rows = cur.fetchall()
    expected_name, expected_columns = EXPECTED_PRIMARY_KEYS[table]
    assert rows, f"no primary key found for {table}"
    assert {name for name, _ in rows} == {expected_name}
    assert [column for _, column in rows] == expected_columns


# ==== Step 9: unique constraints ====

def test_no_unique_constraints_beyond_the_primary_keys(migrated_db_connection):
    # ADR-015: forward mapping uniqueness and Season natural-key
    # uniqueness are delivered by their composite PRIMARY KEYs, not a
    # separate UNIQUE constraint -- confirm none exists.
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' AND constraint_type = 'UNIQUE'"
        )
        rows = cur.fetchall()
    assert rows == []


# ==== Step 10: foreign keys ====

def test_foreign_keys(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "SELECT tc.constraint_name, tc.table_name, kcu.column_name, "
            "       ccu.table_name AS ref_table, ccu.column_name AS ref_column, "
            "       rc.delete_rule, rc.update_rule "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema "
            "JOIN information_schema.referential_constraints rc "
            "  ON tc.constraint_name = rc.constraint_name AND tc.table_schema = rc.constraint_schema "
            "WHERE tc.table_schema = 'public' AND tc.constraint_type = 'FOREIGN KEY'"
        )
        rows = cur.fetchall()

    assert len(rows) == 1, f"expected exactly one foreign key in the whole schema, found {rows!r}"
    name, table, column, ref_table, ref_column, delete_rule, update_rule = rows[0]
    assert name == "seasons_competition_id_fkey"
    assert table == "seasons"
    assert column == "competition_id"
    assert ref_table == "competitions"
    assert ref_column == "competition_id"
    assert delete_rule == "RESTRICT"
    assert update_rule == "NO ACTION"


# ==== Step 11: CHECK constraints (catalog existence) ====

@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_check_constraints_exist(migrated_db_connection, table):
    # information_schema.table_constraints reports PostgreSQL 17's new
    # catalog-level NOT NULL constraints (pg_constraint.contype = 'n') as
    # constraint_type = 'CHECK' too, per SQL-standard reporting -- so it
    # cannot distinguish this migration's actual named CHECK constraints
    # from the auto-generated "<oid>_<oid>_<n>_not_null" entries PG17
    # creates for every NOT NULL column. pg_constraint.contype = 'c' is
    # the precise filter for a genuine CHECK constraint.
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE connamespace = 'public'::regnamespace AND conrelid = %s::regclass AND contype = 'c'",
            (table,),
        )
        actual = {row[0] for row in cur.fetchall()}
    assert actual == EXPECTED_CHECK_CONSTRAINTS[table]


# ==== Step 12: constraint behavior (real INSERT attempts, rolled back) ====

def test_competitions_valid_insert_succeeds(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO competitions (competition_id, name, country) VALUES (%s, %s, %s)",
            ("serie-a", "Serie A", "Italy"),
        )
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("no-country", "No Country"))


def test_competitions_duplicate_id_rejected(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("dup", "First"))
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("dup", "Second"))


@pytest.mark.parametrize(
    "competition_id,name,country",
    [
        ("", "Serie A", None),
        ("   ", "Serie A", None),
        ("serie-a", "", None),
        ("serie-a", "   ", None),
        ("serie-a", "Serie A", ""),
        ("serie-a", "Serie A", "   "),
    ],
    ids=["blank-id", "whitespace-id", "blank-name", "whitespace-name", "blank-country", "whitespace-country"],
)
def test_competitions_nonblank_checks_rejected(migrated_db_connection, competition_id, name, country):
    with migrated_db_connection.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO competitions (competition_id, name, country) VALUES (%s, %s, %s)",
                (competition_id, name, country),
            )


def test_teams_valid_insert_succeeds(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO teams (team_id, name, country, national) VALUES (%s, %s, %s, %s)",
            ("t1", "Inter", "Italy", False),
        )
        cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, %s)", ("t2", "Some Team"))


@pytest.mark.parametrize("national", [None, True, False])
def test_teams_national_accepts_none_and_both_bools(migrated_db_connection, national):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO teams (team_id, name, national) VALUES (%s, %s, %s)",
            ("t-national", "Team", national),
        )


@pytest.mark.parametrize(
    "team_id,name,country",
    [
        ("", "Inter", None),
        ("   ", "Inter", None),
        ("t1", "", None),
        ("t1", "   ", None),
        ("t1", "Inter", ""),
        ("t1", "Inter", "   "),
    ],
    ids=["blank-id", "whitespace-id", "blank-name", "whitespace-name", "blank-country", "whitespace-country"],
)
def test_teams_nonblank_checks_rejected(migrated_db_connection, team_id, name, country):
    with migrated_db_connection.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO teams (team_id, name, country) VALUES (%s, %s, %s)",
                (team_id, name, country),
            )


def test_teams_duplicate_id_rejected(migrated_db_connection):
    # Task 0.5.10F Fix 1: closes the coverage gap the 0.5.10E.1 review
    # found -- Competition/Season/mapping each already had a dedicated
    # duplicate-PK test; Team did not. Both rows use otherwise-valid,
    # nonblank metadata so the only constraint either INSERT can violate
    # is the primary key itself.
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, %s)", ("dup-team", "First"))
        with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
            cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, %s)", ("dup-team", "Second"))
    assert excinfo.value.diag.constraint_name == "teams_pkey"


def test_season_insert_succeeds_for_existing_competition(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("comp-1", "Comp One"))
        cur.execute(
            "INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)",
            ("comp-1", 2025),
        )


def test_season_insert_fails_for_missing_competition(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)",
                ("does-not-exist", 2025),
            )


def test_season_duplicate_natural_key_rejected(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("comp-2", "Comp Two"))
        cur.execute("INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)", ("comp-2", 2025))
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute("INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)", ("comp-2", 2025))


@pytest.mark.parametrize("start_year", [1000, 9999])
def test_season_start_year_boundaries_accepted(migrated_db_connection, start_year):
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("comp-boundary", "Comp"))
        cur.execute(
            "INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)",
            ("comp-boundary", start_year),
        )


@pytest.mark.parametrize("start_year", [999, 10000])
def test_season_start_year_out_of_range_rejected(migrated_db_connection, start_year):
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("comp-range", "Comp"))
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)",
                ("comp-range", start_year),
            )


def test_competition_deletion_restricted_by_existing_season(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute("INSERT INTO competitions (competition_id, name) VALUES (%s, %s)", ("comp-restrict", "Comp"))
        cur.execute(
            "INSERT INTO seasons (competition_id, start_year) VALUES (%s, %s)",
            ("comp-restrict", 2025),
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute("DELETE FROM competitions WHERE competition_id = %s", ("comp-restrict",))


def test_mapping_valid_insert_succeeds(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO provider_identity_mappings (provider, entity_type, provider_entity_id, footcap_entity_id) "
            "VALUES (%s, %s, %s, %s)",
            ("api-football", "team", "505", "team-internal-1"),
        )


def test_mapping_forward_conflict_rejected(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO provider_identity_mappings (provider, entity_type, provider_entity_id, footcap_entity_id) "
            "VALUES (%s, %s, %s, %s)",
            ("api-football", "team", "505", "team-internal-1"),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO provider_identity_mappings "
                "(provider, entity_type, provider_entity_id, footcap_entity_id) VALUES (%s, %s, %s, %s)",
                ("api-football", "team", "505", "team-internal-2"),
            )


def test_mapping_reverse_many_to_one_accepted(migrated_db_connection):
    # ADR-012/ADR-015: distinct provider references may map to the same
    # FootCap identity, including within the same provider/entity_type.
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO provider_identity_mappings (provider, entity_type, provider_entity_id, footcap_entity_id) "
            "VALUES (%s, %s, %s, %s)",
            ("api-football", "team", "505", "team-internal-1"),
        )
        cur.execute(
            "INSERT INTO provider_identity_mappings (provider, entity_type, provider_entity_id, footcap_entity_id) "
            "VALUES (%s, %s, %s, %s)",
            ("api-football", "team", "999", "team-internal-1"),
        )


def test_mapping_exact_string_semantics_no_normalization(migrated_db_connection):
    with migrated_db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO provider_identity_mappings (provider, entity_type, provider_entity_id, footcap_entity_id) "
            "VALUES (%s, %s, %s, %s)",
            ("api-football", "team", "505", "team-a"),
        )
        # "0505" must remain a distinct row from "505" -- no leading-zero
        # normalization anywhere in the schema (plain TEXT columns).
        cur.execute(
            "INSERT INTO provider_identity_mappings (provider, entity_type, provider_entity_id, footcap_entity_id) "
            "VALUES (%s, %s, %s, %s)",
            ("api-football", "team", "0505", "team-b"),
        )
        cur.execute(
            "SELECT provider_entity_id FROM provider_identity_mappings "
            "WHERE provider = 'api-football' AND entity_type = 'team' ORDER BY provider_entity_id"
        )
        assert [row[0] for row in cur.fetchall()] == ["0505", "505"]


@pytest.mark.parametrize(
    "provider,entity_type,provider_entity_id,footcap_entity_id",
    [
        ("", "team", "1", "x"),
        ("api-football", "", "1", "x"),
        ("api-football", "team", "", "x"),
        ("api-football", "team", "1", ""),
    ],
    ids=["blank-provider", "blank-entity-type", "blank-provider-entity-id", "blank-footcap-entity-id"],
)
def test_mapping_nonblank_checks_rejected(migrated_db_connection, provider, entity_type, provider_entity_id, footcap_entity_id):
    with migrated_db_connection.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO provider_identity_mappings "
                "(provider, entity_type, provider_entity_id, footcap_entity_id) VALUES (%s, %s, %s, %s)",
                (provider, entity_type, provider_entity_id, footcap_entity_id),
            )


# ==== Task 0.5.10F Fix 2/3: entity + first mapping atomicity ====
#
# ADR-013 decision 7 / ADR-015 decisions 8/10: creating a Team and its
# first ProviderIdentityMapping must behave as one logical atomic
# operation -- a successful operation exposes both rows, or neither.
# These two tests deliberately use real, independently-committing
# connections (via conftest.py's `_open_connection`, always derived from
# the already-safety-gated `test_database_url` fixture -- never a raw
# env-var read) rather than migrated_db_connection, because proving
# "durable success" and "durable non-existence after rollback" both
# require verifying state from outside the transaction under test, which
# migrated_db_connection's always-rollback design cannot do. Both tests
# depend on `migrated_database` directly (not merely `migrated_db_connection`)
# since neither uses that fixture's connection.

def test_team_mapping_atomic_success_is_durable(migrated_database, test_database_url):
    team_id = f"t-atomic-{uuid.uuid4().hex}"
    provider_entity_id = uuid.uuid4().hex

    connection = _open_connection(test_database_url)
    try:
        with connection.cursor() as cur:
            cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, %s)", (team_id, "Atomic Team"))
            cur.execute(
                "INSERT INTO provider_identity_mappings "
                "(provider, entity_type, provider_entity_id, footcap_entity_id) VALUES (%s, %s, %s, %s)",
                ("api-football", "team", provider_entity_id, team_id),
            )
        connection.commit()

        # Verify durability from a fresh, independent connection -- not
        # merely that the two INSERTs succeeded within their own
        # transaction, which every uncommitted transaction trivially sees
        # regardless of whether it is ever actually committed.
        verify_connection = _open_connection(test_database_url)
        try:
            with verify_connection.cursor() as cur:
                cur.execute("SELECT 1 FROM teams WHERE team_id = %s", (team_id,))
                assert cur.fetchone() is not None, "committed Team row is not durably visible"

                cur.execute(
                    "SELECT footcap_entity_id FROM provider_identity_mappings "
                    "WHERE provider = %s AND entity_type = %s AND provider_entity_id = %s",
                    ("api-football", "team", provider_entity_id),
                )
                row = cur.fetchone()
                assert row is not None, "committed mapping row is not durably visible"
                assert row[0] == team_id
        finally:
            verify_connection.close()
    finally:
        # Cleanup: remove only the exact rows this test committed. Never
        # TRUNCATE or reset the schema -- other db-marked tests in this
        # session share the same migrated database.
        with connection.cursor() as cur:
            cur.execute(
                "DELETE FROM provider_identity_mappings "
                "WHERE provider = %s AND entity_type = %s AND provider_entity_id = %s",
                ("api-football", "team", provider_entity_id),
            )
            cur.execute("DELETE FROM teams WHERE team_id = %s", (team_id,))
        connection.commit()
        connection.close()


def test_team_mapping_failure_leaves_no_orphan_team(migrated_database, test_database_url):
    occupied_provider_entity_id = uuid.uuid4().hex
    new_team_id = f"t-orphan-{uuid.uuid4().hex}"

    # Step 1: pre-establish and durably commit the mapping key the main
    # transaction's mapping insert will collide against -- decoupled from
    # the transaction under test, mirroring a genuine "another bootstrap
    # run already holds this provider reference" scenario rather than a
    # same-transaction self-conflict.
    setup_connection = _open_connection(test_database_url)
    try:
        with setup_connection.cursor() as cur:
            cur.execute(
                "INSERT INTO provider_identity_mappings "
                "(provider, entity_type, provider_entity_id, footcap_entity_id) VALUES (%s, %s, %s, %s)",
                ("api-football", "team", occupied_provider_entity_id, "team-already-mapped"),
            )
        setup_connection.commit()
    finally:
        setup_connection.close()

    try:
        # Steps 2-5: a fresh transaction inserts a brand-new Team (this
        # INSERT alone would succeed), then attempts a mapping insert
        # against the already-occupied provider reference (this INSERT
        # must fail on the mapping's own primary key, not on any other
        # constraint).
        main_connection = _open_connection(test_database_url)
        try:
            with main_connection.cursor() as cur:
                cur.execute("INSERT INTO teams (team_id, name) VALUES (%s, %s)", (new_team_id, "Orphan Candidate"))

                with pytest.raises(psycopg.errors.UniqueViolation) as excinfo:
                    cur.execute(
                        "INSERT INTO provider_identity_mappings "
                        "(provider, entity_type, provider_entity_id, footcap_entity_id) VALUES (%s, %s, %s, %s)",
                        ("api-football", "team", occupied_provider_entity_id, new_team_id),
                    )
                assert excinfo.value.diag.constraint_name == "provider_identity_mappings_pkey"

            # Step 6: roll back the WHOLE transaction -- this is what
            # must discard the otherwise-successful Team insert alongside
            # the failed mapping insert.
            main_connection.rollback()
        finally:
            main_connection.close()

        # Step 7 (the core orphan-prevention assertion): from a separate,
        # fresh connection -- never merely trusting that "the mapping
        # insert failed" implies the Team was also discarded -- prove the
        # candidate Team never became durable.
        verify_connection = _open_connection(test_database_url)
        try:
            with verify_connection.cursor() as cur:
                cur.execute("SELECT 1 FROM teams WHERE team_id = %s", (new_team_id,))
                assert cur.fetchone() is None, (
                    "orphan Team row survived a rolled-back transaction whose mapping insert failed"
                )
        finally:
            verify_connection.close()
    finally:
        # Cleanup: remove only the durably-committed setup row. The
        # candidate Team row was never committed, so there is nothing to
        # delete for it -- its absence is exactly what this test proves.
        cleanup_connection = _open_connection(test_database_url)
        try:
            with cleanup_connection.cursor() as cur:
                cur.execute(
                    "DELETE FROM provider_identity_mappings "
                    "WHERE provider = %s AND entity_type = %s AND provider_entity_id = %s",
                    ("api-football", "team", occupied_provider_entity_id),
                )
            cleanup_connection.commit()
        finally:
            cleanup_connection.close()
