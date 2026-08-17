"""PostgresSeasonRepository (Task 0.5.11E; ADR-014).

Implements SeasonRepository.get() and get_or_create(). get_or_create uses
INSERT ... ON CONFLICT (natural key) DO NOTHING RETURNING ..., never a
SELECT-first-then-INSERT sequence, so idempotent-existing-key and
concurrent-identical-creation both resolve without any error surfaced to
either caller (mirrors the ON CONFLICT / row-lock reasoning ADR-015
decision 11 and Task 0.5.10G already proved for the mapping table's own
forward-uniqueness race). No SERIALIZABLE isolation, advisory lock,
SELECT FOR UPDATE, or retry loop is used or needed.

This query never joins provider_identity_mappings -- Season has no
provider mapping of its own (ADR-014 decisions 9-10).
"""
from __future__ import annotations

import psycopg

from ...domain.season import Season
from ..errors import ReferencedEntityNotFoundError
from ._connection import ConnectionFactory
from ._errors import _raise_repository_error
from ._rows import _season_from_row

_SELECT_SEASON = "SELECT competition_id, start_year FROM public.seasons WHERE competition_id = %s AND start_year = %s"

_INSERT_SEASON_IF_ABSENT = (
    "INSERT INTO public.seasons (competition_id, start_year) VALUES (%s, %s) "
    "ON CONFLICT (competition_id, start_year) DO NOTHING "
    "RETURNING competition_id, start_year"
)


class PostgresSeasonRepository:
    """SeasonRepository.get()/get_or_create() over a real PostgreSQL
    connection.

    Opens and closes its own connection per call (via `connection_factory`)
    -- never receives, shares, or exposes a connection, cursor, or
    transaction across calls."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def get(self, competition_id: str, start_year: int) -> Season | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cur:
                cur.execute(_SELECT_SEASON, (competition_id, start_year))
                row = cur.fetchone()
            connection.commit()
        except Exception as exc:
            connection.rollback()
            _raise_repository_error(exc)
        finally:
            connection.close()
        if row is None:
            return None
        return _season_from_row(row)

    def get_or_create(self, season: Season) -> Season:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cur:
                try:
                    cur.execute(_INSERT_SEASON_IF_ABSENT, (season.competition_id, season.start_year))
                except psycopg.errors.ForeignKeyViolation:
                    connection.rollback()
                    raise ReferencedEntityNotFoundError("competition", season.competition_id) from None
                row = cur.fetchone()
                if row is None:
                    # ON CONFLICT DO NOTHING suppressed the insert: the
                    # natural key already existed. Idempotent success --
                    # read the existing row back inside the same
                    # transaction rather than assuming what it contains.
                    cur.execute(_SELECT_SEASON, (season.competition_id, season.start_year))
                    row = cur.fetchone()
            connection.commit()
        except ReferencedEntityNotFoundError:
            raise
        except Exception as exc:
            connection.rollback()
            _raise_repository_error(exc)
        finally:
            connection.close()
        return _season_from_row(row)
