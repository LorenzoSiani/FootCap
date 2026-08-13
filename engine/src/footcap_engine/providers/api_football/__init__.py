"""
Public boundary for the API-Football provider (ADR-011: Provider
Identity and Raw Observation Boundary). Only the names re-exported here
are part of the stable Phase 0 API this slice provides; parsing/hash
helpers in client.py and models.py are private implementation detail.
"""
from .client import ApiFootballClient
from .models import (
    ApiFootballConfig,
    ApiFootballError,
    ApiFootballHttpError,
    ApiFootballLeague,
    ApiFootballMalformedResponseError,
    ApiFootballProviderError,
    HttpRequestIdentity,
    LeagueFetchResult,
    LogicalRequestIdentity,
    RawContent,
    RawObservation,
)

__all__ = [
    "ApiFootballClient",
    "ApiFootballConfig",
    "ApiFootballError",
    "ApiFootballHttpError",
    "ApiFootballLeague",
    "ApiFootballMalformedResponseError",
    "ApiFootballProviderError",
    "HttpRequestIdentity",
    "LeagueFetchResult",
    "LogicalRequestIdentity",
    "RawContent",
    "RawObservation",
]
