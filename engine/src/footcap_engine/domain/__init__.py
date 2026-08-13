"""
Public boundary for FootCap-internal domain concepts not owned by one
provider, one job type, or one wire contract (ADR-012). Only the names
re-exported here are part of the stable Phase 0 API other engine modules
may depend on; everything else in identity.py is a private implementation
detail.
"""
from .identity import (
    IdentityInputError,
    IdentityResolver,
    ProviderEntityRef,
    ProviderIdentityMapping,
    UnresolvedProviderIdentityError,
)

__all__ = [
    "IdentityInputError",
    "IdentityResolver",
    "ProviderEntityRef",
    "ProviderIdentityMapping",
    "UnresolvedProviderIdentityError",
]
