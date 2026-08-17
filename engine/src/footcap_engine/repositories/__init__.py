"""
Public boundary for FootCap's repository-layer contracts (Task 0.5.11A;
restructured by Task 0.5.11A.1; ADR-012, ADR-013, ADR-014, ADR-015).
These are structural typing.Protocol definitions only -- no PostgreSQL,
SQL, connection/cursor, Supabase client, UnitOfWork/transaction manager,
or other implementation detail appears anywhere in this package. A future
concrete implementation (e.g. a PostgreSQL-backed repository) lives
elsewhere and satisfies these contracts; none is provided here.

Only the names re-exported here are part of the stable Phase 0 API other
engine modules may depend on.
"""
from .competition import CompetitionMappingCreation, CompetitionRepository
from .errors import (
    EntityAlreadyExistsError,
    ProviderMappingConflictError,
    ReferencedEntityNotFoundError,
    RepositoryError,
)
from .mapping import ProviderIdentityMappingRepository, UnresolvedProviderIdentityError
from .season import SeasonRepository
from .team import TeamMappingCreation, TeamRepository

__all__ = [
    "CompetitionMappingCreation",
    "CompetitionRepository",
    "EntityAlreadyExistsError",
    "ProviderIdentityMappingRepository",
    "ProviderMappingConflictError",
    "ReferencedEntityNotFoundError",
    "RepositoryError",
    "SeasonRepository",
    "TeamMappingCreation",
    "TeamRepository",
    "UnresolvedProviderIdentityError",
]
