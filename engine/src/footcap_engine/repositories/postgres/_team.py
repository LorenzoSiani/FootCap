"""PostgresTeamRepository (Task 0.5.11E; ADR-013; ADR-015 decision 4).

Implements only TeamRepository.get(). No create/update/delete operation
lives here -- Team creation-with-mapping remains unimplemented
(TeamMappingCreation is not addressed by this task). This query never
joins Competition or Season -- Team identity is Competition- and
Season-independent (ADR-013 decision 4).
"""
from __future__ import annotations

from ...domain.team import Team
from ._connection import ConnectionFactory
from ._errors import _raise_repository_error
from ._rows import _team_from_row

_SELECT_TEAM = "SELECT team_id, name, country, national FROM public.teams WHERE team_id = %s"


class PostgresTeamRepository:
    """TeamRepository.get() over a real PostgreSQL connection.

    Opens and closes its own connection per call (via `connection_factory`)
    -- never receives, shares, or exposes a connection, cursor, or
    transaction across calls."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def get(self, team_id: str) -> Team | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cur:
                cur.execute(_SELECT_TEAM, (team_id,))
                row = cur.fetchone()
            connection.commit()
        except Exception as exc:
            connection.rollback()
            _raise_repository_error(exc)
        finally:
            connection.close()
        if row is None:
            return None
        return _team_from_row(row)
