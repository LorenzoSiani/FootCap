"""PostgreSQL adapter implementations for FootCap's repository contracts.

Task 0.5.11E adds the first concrete repositories: read-only Competition
and Team lookups, and Season's get()/get_or_create(). Provider identity
mapping and entity-plus-first-mapping creation (CompetitionMappingCreation,
TeamMappingCreation, ProviderIdentityMappingRepository) remain
unimplemented here.
"""

from ._competition import PostgresCompetitionRepository
from ._connection import ConnectionFactory
from ._season import PostgresSeasonRepository
from ._team import PostgresTeamRepository

__all__ = [
    "ConnectionFactory",
    "PostgresCompetitionRepository",
    "PostgresSeasonRepository",
    "PostgresTeamRepository",
]
