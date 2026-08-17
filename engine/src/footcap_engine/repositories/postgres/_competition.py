"""PostgresCompetitionRepository (Task 0.5.11E; ADR-013; ADR-015 decision 3).

Implements only CompetitionRepository.get(). No create/update/delete
operation lives here -- Competition creation-with-mapping remains
unimplemented (CompetitionMappingCreation is not addressed by this task).
"""
from __future__ import annotations

from ...domain.competition import Competition
from ._connection import ConnectionFactory
from ._errors import _raise_repository_error
from ._rows import _competition_from_row

_SELECT_COMPETITION = "SELECT competition_id, name, country FROM public.competitions WHERE competition_id = %s"


class PostgresCompetitionRepository:
    """CompetitionRepository.get() over a real PostgreSQL connection.

    Opens and closes its own connection per call (via `connection_factory`)
    -- never receives, shares, or exposes a connection, cursor, or
    transaction across calls."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def get(self, competition_id: str) -> Competition | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cur:
                cur.execute(_SELECT_COMPETITION, (competition_id,))
                row = cur.fetchone()
            connection.commit()
        except Exception as exc:
            connection.rollback()
            _raise_repository_error(exc)
        finally:
            connection.close()
        if row is None:
            return None
        return _competition_from_row(row)
