"""
Public boundary for FootCap's repository-layer contracts (Task 0.5.11A;
restructured by Task 0.5.11A.1; ADR-012, ADR-013, ADR-014, ADR-015).
The names exported here remain database-neutral: PostgreSQL plumbing is
isolated in the repositories.postgres implementation package and is not
re-exported through this boundary. No concrete repository is provided yet.

Only the names re-exported here are part of the stable Phase 0 API other
engine modules may depend on.
"""
from .competition import CompetitionMappingCreation, CompetitionRepository
from .errors import (
    EntityAlreadyExistsError,
    ProviderMappingConflictError,
    ReferencedEntityNotFoundError,
    RepositoryError,
    RepositoryOperationError,
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
    "RepositoryOperationError",
    "SeasonRepository",
    "TeamMappingCreation",
    "TeamRepository",
    "UnresolvedProviderIdentityError",
]
