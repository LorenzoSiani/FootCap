"""
API-Football provider values (ADR-011: Provider Identity and Raw
Observation Boundary).

This module implements only the Provider layer: HTTP transport
configuration, exact raw-response capture, the request-identity
concepts ADR-011 requires, provider envelope classification, and a
provider-shaped League DTO. It does not implement identity resolution,
FootCap domain/normalized facts, Temporal Engine integration, or
RunProvenance orchestration -- those are explicitly later tasks.

No database, network, or filesystem access. No global mutable state.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from urllib.parse import urlsplit

PROVIDER_NAME = "api-football"

# Direct API-Sports (not RapidAPI) origin. Phase 0.5.1F fix: base_url is
# intentionally constrained to exactly this origin so the client can
# never be pointed at an arbitrary host that would still receive the
# x-apisports-key header (see ApiFootballConfig.__post_init__). Exact
# hostname equality after urlsplit() is deliberately simple -- no
# configurable allowlist framework, no DNS resolution -- because this
# slice only ever needs to support one origin.
_ALLOWED_API_FOOTBALL_HOST = "v3.football.api-sports.io"


class ApiFootballError(ValueError):
    """Base for all api_football provider errors: malformed/invalid
    input to this module's constructors, and (via subclasses) HTTP/
    envelope/provider response failures. Never carries the API key."""

    def __init__(self, message: str, *, observation: "RawObservation | None" = None) -> None:
        super().__init__(message)
        self.observation = observation


class ApiFootballHttpError(ApiFootballError):
    """A response was actually received but its HTTP status was not
    2xx. `.observation` remains available (raw bytes are captured
    before status classification) so a provider-error path never loses
    the raw observation ADR-011 requires."""

    def __init__(self, status_code: int, *, observation: "RawObservation | None" = None) -> None:
        super().__init__(f"API-Football returned HTTP status {status_code}", observation=observation)
        self.status_code = status_code


class ApiFootballMalformedResponseError(ApiFootballError):
    """The response body did not parse as JSON, or the parsed JSON did
    not match the documented envelope/DTO shape."""


class ApiFootballProviderError(ApiFootballError):
    """The provider's own envelope declared a semantic error (non-empty
    `errors`) despite a successful HTTP status."""

    def __init__(self, provider_errors: object, *, observation: "RawObservation | None" = None) -> None:
        super().__init__(f"API-Football reported provider errors: {provider_errors!r}", observation=observation)
        self.provider_errors = provider_errors


def _validate_non_blank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ApiFootballError(f"{field_name} must be a string, got {type(value)!r}")
    if value.strip() == "":
        raise ApiFootballError(f"{field_name} must not be blank or whitespace-only")
    return value


def _ensure_utc(value: object, field_name: str) -> datetime:
    """Reject non-datetime input and naive/pseudo-aware datetimes;
    normalize any genuinely timezone-aware datetime to UTC. Mirrors
    footcap_engine.temporal.evaluation._ensure_utc /
    footcap_engine.runs.provenance._ensure_utc."""
    if not isinstance(value, datetime):
        raise ApiFootballError(f"{field_name} must be a datetime.datetime, got {type(value)!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiFootballError(
            f"{field_name} must be a timezone-aware datetime; naive or pseudo-aware "
            "datetimes are rejected"
        )
    return value.astimezone(timezone.utc)


def _validate_base_url(value: object) -> str:
    """Constrain base_url to exactly the direct API-Sports HTTPS origin
    (0.5.1F fix 1): https scheme, no userinfo, no explicit port, host
    equal to _ALLOWED_API_FOOTBALL_HOST exactly, and no path beyond an
    optional trailing slash / no query / no fragment. Rejects RapidAPI
    hosts, HTTP, foreign hosts, and lookalike/suffix domains such as
    "v3.football.api-sports.io.example.com" (whose parsed hostname is
    that whole string, not the allowed host)."""
    _validate_non_blank_string(value, "base_url")
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise ApiFootballError("base_url must use the https scheme")
    if parsed.username is not None or parsed.password is not None:
        raise ApiFootballError("base_url must not contain userinfo")
    if parsed.port is not None:
        raise ApiFootballError("base_url must not specify a port")
    if parsed.hostname != _ALLOWED_API_FOOTBALL_HOST:
        raise ApiFootballError(
            f"base_url host must be exactly {_ALLOWED_API_FOOTBALL_HOST!r}, got {parsed.hostname!r}"
        )
    if parsed.path not in ("", "/"):
        raise ApiFootballError("base_url must not contain a path")
    if parsed.query or parsed.fragment:
        raise ApiFootballError("base_url must not contain a query or fragment")
    return value


def _fingerprint(body: bytes) -> str:
    """Integrity/content-address fingerprint over exact raw bytes.
    SHA-256 via stdlib hashlib is a Phase 0 implementation choice --
    ADR-011 deliberately does not freeze the hash algorithm."""
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class ApiFootballConfig:
    """Direct API-Sports (not RapidAPI) connection configuration. The
    caller supplies the API key; this client never reads environment
    variables and never defaults or discovers a key. api_key is
    excluded from the generated __repr__ so it can never leak into
    logs/debuggers via repr()."""

    api_key: str = field(repr=False)
    base_url: str = "https://v3.football.api-sports.io"
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _validate_non_blank_string(self.api_key, "api_key")
        _validate_base_url(self.base_url)
        for name, value in (
            ("connect_timeout_seconds", self.connect_timeout_seconds),
            ("read_timeout_seconds", self.read_timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ApiFootballError(f"{name} must be a number, got {type(value)!r}")
            if not math.isfinite(value) or value <= 0:
                raise ApiFootballError(f"{name} must be a positive, finite number")


@dataclass(frozen=True)
class RawContent:
    """Exact, immutable HTTP response body bytes plus an integrity
    fingerprint computed from those exact bytes (ADR-011 decisions 6,
    9). content_fingerprint is always derived from body -- never
    independently supplied -- so the two can never be constructed out
    of sync."""

    body: bytes
    content_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.body, bytes):
            raise ApiFootballError(f"body must be bytes, got {type(self.body)!r}")
        object.__setattr__(self, "content_fingerprint", _fingerprint(self.body))


@dataclass(frozen=True)
class LogicalRequestIdentity:
    """provider + endpoint + normalized semantic filters (ADR-011
    decision 10). Excludes credentials, execution timestamp, retry
    attempt, and pagination page by construction -- callers never pass
    those in. Parameters are canonicalized by sorted-key order so
    construction order never affects equality."""

    provider: str
    endpoint: str
    parameters: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _validate_non_blank_string(self.provider, "provider")
        _validate_non_blank_string(self.endpoint, "endpoint")
        if not isinstance(self.parameters, tuple):
            raise ApiFootballError("parameters must be a tuple of (str, str) pairs")
        for pair in self.parameters:
            if not (isinstance(pair, tuple) and len(pair) == 2 and all(isinstance(item, str) for item in pair)):
                raise ApiFootballError("each parameters entry must be a (str, str) pair")
        object.__setattr__(self, "parameters", tuple(sorted(self.parameters)))


@dataclass(frozen=True)
class HttpRequestIdentity:
    """Identifies one individual HTTP call/page within a logical
    request series (ADR-011 decision 10), distinct from
    LogicalRequestIdentity. This slice has neither pagination nor
    retries, so no page/attempt field is added yet -- adding one
    speculatively would invent semantics no current behavior needs."""

    logical_request: LogicalRequestIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.logical_request, LogicalRequestIdentity):
            raise ApiFootballError("logical_request must be a LogicalRequestIdentity")


@dataclass(frozen=True)
class RawObservation:
    """Exactly one actual provider HTTP response occurrence (ADR-011
    decision 5). Two observations may share identical RawContent (and
    therefore an identical content fingerprint) while remaining
    distinct observations (ADR-011 decision 7) -- nothing here collapses
    them; distinctness is carried by requested_at/received_at/
    job_run_id/http_request, not by content."""

    provider: str
    endpoint: str
    logical_request: LogicalRequestIdentity
    http_request: HttpRequestIdentity
    request_parameters: Mapping[str, str]
    requested_at: datetime
    received_at: datetime
    http_status: int
    job_run_id: str
    raw_content: RawContent

    def __post_init__(self) -> None:
        provider = _validate_non_blank_string(self.provider, "provider")
        endpoint = _validate_non_blank_string(self.endpoint, "endpoint")

        if not isinstance(self.logical_request, LogicalRequestIdentity):
            raise ApiFootballError("logical_request must be a LogicalRequestIdentity")
        if not isinstance(self.http_request, HttpRequestIdentity):
            raise ApiFootballError("http_request must be a HttpRequestIdentity")
        if self.http_request.logical_request != self.logical_request:
            raise ApiFootballError("http_request.logical_request must match logical_request")
        if provider != self.logical_request.provider or endpoint != self.logical_request.endpoint:
            raise ApiFootballError("provider/endpoint must match logical_request's provider/endpoint")

        if not isinstance(self.request_parameters, Mapping):
            raise ApiFootballError(f"request_parameters must be a mapping, got {type(self.request_parameters)!r}")
        frozen_parameters: dict[str, str] = {}
        for key, value in self.request_parameters.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ApiFootballError("request_parameters keys and values must be strings")
            frozen_parameters[key] = value

        # 0.5.1F fix 2: request_parameters must agree exactly (by semantic
        # key/value content, not object identity) with logical_request's
        # own normalized parameters -- otherwise this immutable
        # provenance record could describe two different requests at
        # once. Compared as sorted (key, value) tuples, matching
        # LogicalRequestIdentity's own canonical sorted-tuple form.
        if tuple(sorted(frozen_parameters.items())) != self.logical_request.parameters:
            raise ApiFootballError(
                "request_parameters must exactly match logical_request.parameters: "
                f"{sorted(frozen_parameters.items())!r} != {list(self.logical_request.parameters)!r}"
            )

        requested_at = _ensure_utc(self.requested_at, "requested_at")
        received_at = _ensure_utc(self.received_at, "received_at")
        if received_at < requested_at:
            raise ApiFootballError("received_at must not be before requested_at")

        if isinstance(self.http_status, bool) or not isinstance(self.http_status, int):
            raise ApiFootballError(f"http_status must be an int, got {type(self.http_status)!r}")
        if not (100 <= self.http_status <= 599):
            raise ApiFootballError("http_status must be a valid HTTP status code (100-599)")

        job_run_id = _validate_non_blank_string(self.job_run_id, "job_run_id")

        if not isinstance(self.raw_content, RawContent):
            raise ApiFootballError("raw_content must be a RawContent")

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "request_parameters", MappingProxyType(frozen_parameters))
        object.__setattr__(self, "requested_at", requested_at)
        object.__setattr__(self, "received_at", received_at)
        object.__setattr__(self, "job_run_id", job_run_id)


@dataclass(frozen=True)
class ApiFootballLeague:
    """Provider-shaped League DTO. Deliberately NOT a FootCap normalized
    Competition -- it retains the provider's own league ID, and ADR-011
    identity resolution into a FootCap competition identity is
    explicitly future work, not implemented here."""

    provider_league_id: int
    name: str
    type: str
    logo: str | None
    country_name: str | None

    def __post_init__(self) -> None:
        if isinstance(self.provider_league_id, bool) or not isinstance(self.provider_league_id, int):
            raise ApiFootballMalformedResponseError(
                f"league.id must be an int, got {type(self.provider_league_id)!r}"
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise ApiFootballMalformedResponseError(f"league.name must be a non-blank string, got {self.name!r}")
        if not isinstance(self.type, str) or not self.type.strip():
            raise ApiFootballMalformedResponseError(f"league.type must be a non-blank string, got {self.type!r}")
        if self.logo is not None and not isinstance(self.logo, str):
            raise ApiFootballMalformedResponseError("league.logo must be a string or None")
        if self.country_name is not None and not isinstance(self.country_name, str):
            raise ApiFootballMalformedResponseError("country.name must be a string or None")


@dataclass(frozen=True)
class LeagueFetchResult:
    """Result of one get_league() call. The raw observation always
    remains available for a successful HTTP response, even when the
    provider's response list is empty (ADR-011: raw provenance is never
    discarded)."""

    observation: RawObservation
    league: ApiFootballLeague | None

    def __post_init__(self) -> None:
        if not isinstance(self.observation, RawObservation):
            raise ApiFootballError("observation must be a RawObservation")
        if self.league is not None and not isinstance(self.league, ApiFootballLeague):
            raise ApiFootballError("league must be an ApiFootballLeague or None")
