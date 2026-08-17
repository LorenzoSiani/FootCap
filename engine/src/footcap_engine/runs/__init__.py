"""
Public boundary for the FootCap Run / Provenance Engine (Architecture
Baseline section 13; ADR-010). Only the names re-exported here are part of
the stable Phase 0 API other engine modules may depend on; everything else
in provenance.py is a private implementation detail.
"""
from .provenance import (
    ExecutionContext,
    ExecutionOrigin,
    JobType,
    RunInputError,
    RunProvenance,
    RunStatus,
    WorkingTreeState,
    validate_run_provenance,
)

__all__ = [
    "ExecutionContext",
    "ExecutionOrigin",
    "JobType",
    "RunInputError",
    "RunProvenance",
    "RunStatus",
    "WorkingTreeState",
    "validate_run_provenance",
]
