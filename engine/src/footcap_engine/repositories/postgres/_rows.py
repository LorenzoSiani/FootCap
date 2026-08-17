"""Explicit PostgreSQL row-to-domain mapping functions."""

from typing import TypeAlias

from ...domain.competition import Competition
from ...domain.season import Season
from ...domain.team import Team

CompetitionRow: TypeAlias = tuple[str, str, str | None]
TeamRow: TypeAlias = tuple[str, str, str | None, bool | None]
SeasonRow: TypeAlias = tuple[str, int]


def _competition_from_row(row: CompetitionRow) -> Competition:
    competition_id, name, country = row
    return Competition(competition_id=competition_id, name=name, country=country)


def _team_from_row(row: TeamRow) -> Team:
    team_id, name, country, national = row
    return Team(team_id=team_id, name=name, country=country, national=national)


def _season_from_row(row: SeasonRow) -> Season:
    competition_id, start_year = row
    return Season(competition_id=competition_id, start_year=start_year)
