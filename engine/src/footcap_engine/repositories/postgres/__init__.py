"""PostgreSQL adapter implementations for FootCap's repository contracts.

Concrete repositories for Competition, Team, Season, and provider identity
mapping. Entity-plus-first-mapping creation remains unimplemented here.
"""

from ._competition import PostgresCompetitionRepository
from ._connection import ConnectionFactory
from ._mapping import PostgresProviderIdentityMappingRepository
from ._season import PostgresSeasonRepository
from ._team import PostgresTeamRepository

__all__ = [
    "ConnectionFactory",
    "PostgresCompetitionRepository",
    "PostgresProviderIdentityMappingRepository",
    "PostgresSeasonRepository",
    "PostgresTeamRepository",
]
