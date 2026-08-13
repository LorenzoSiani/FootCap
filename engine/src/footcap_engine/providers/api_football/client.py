"""
Synchronous API-Football HTTP client (ADR-011: Provider Identity and Raw
Observation Boundary).

First vertical slice: direct API-Sports authentication, one endpoint
(GET /leagues?id=...), exact raw-byte capture before JSON parsing, and
provider envelope classification. No retry, no rate-limit handling, no
pagination, no identity resolution, no normalization, no persistence --
those are later tasks. The client owns HTTP only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from .models import (
    PROVIDER_NAME,
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

_LEAGUES_ENDPOINT = "/leagues"
_ENVELOPE_KEYS = ("get", "parameters", "errors", "results", "paging", "response")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_league_id(league_id: object) -> int:
    if isinstance(league_id, bool) or not isinstance(league_id, int):
        raise ApiFootballError(f"league_id must be an int, got {type(league_id)!r}")
    if league_id <= 0:
        raise ApiFootballError("league_id must be a positive integer")
    return league_id


def _validate_job_run_id(job_run_id: object) -> str:
    if not isinstance(job_run_id, str):
        raise ApiFootballError(f"job_run_id must be a string, got {type(job_run_id)!r}")
    if job_run_id.strip() == "":
        raise ApiFootballError("job_run_id must not be blank or whitespace-only")
    return job_run_id


def _validate_envelope_shape(payload: object, observation: RawObservation) -> dict:
    if not isinstance(payload, dict):
        raise ApiFootballMalformedResponseError("response body is not a JSON object", observation=observation)
    missing = [key for key in _ENVELOPE_KEYS if key not in payload]
    if missing:
        raise ApiFootballMalformedResponseError(
            f"response envelope missing expected key(s): {', '.join(missing)}", observation=observation
        )
    if not isinstance(payload["errors"], (list, dict)):
        raise ApiFootballMalformedResponseError("envelope 'errors' field has an unexpected type", observation=observation)
    if not isinstance(payload["response"], list):
        raise ApiFootballMalformedResponseError("envelope 'response' field is not a list", observation=observation)
    return payload


def _parse_league(entry: object, observation: RawObservation) -> ApiFootballLeague:
    if not isinstance(entry, dict):
        raise ApiFootballMalformedResponseError("response[0] is not an object", observation=observation)
    league_obj = entry.get("league")
    if not isinstance(league_obj, dict):
        raise ApiFootballMalformedResponseError("response[0].league is missing or not an object", observation=observation)
    country_obj = entry.get("country")
    country_name = country_obj.get("name") if isinstance(country_obj, dict) else None

    try:
        return ApiFootballLeague(
            provider_league_id=league_obj.get("id"),
            name=league_obj.get("name"),
            type=league_obj.get("type"),
            logo=league_obj.get("logo"),
            country_name=country_name if isinstance(country_name, str) else None,
        )
    except ApiFootballMalformedResponseError as exc:
        raise ApiFootballMalformedResponseError(str(exc), observation=observation) from exc


class ApiFootballClient:
    """Direct API-Sports client. Synchronous only. Owns base URL, auth
    header injection, timeout configuration, HTTP GET, exact byte
    capture, HTTP status classification, envelope parsing,
    RawObservation construction, and League DTO parsing for this
    slice's single endpoint. Never inspects environment variables and
    never logs the API key."""

    def __init__(self, config: ApiFootballConfig, transport: httpx.BaseTransport | None = None) -> None:
        if not isinstance(config, ApiFootballConfig):
            raise ApiFootballError("config must be an ApiFootballConfig")
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.read_timeout_seconds, connect=config.connect_timeout_seconds),
            headers={"x-apisports-key": config.api_key},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get_league(self, league_id: int, job_run_id: str) -> LeagueFetchResult:
        """GET /leagues?id=<league_id>. Returns a LeagueFetchResult
        whose `observation` is always populated for any successfully
        received HTTP response (ADR-011); `league` is None only for a
        valid, empty provider response list."""
        league_id = _validate_league_id(league_id)
        job_run_id = _validate_job_run_id(job_run_id)

        logical_request = LogicalRequestIdentity(
            provider=PROVIDER_NAME,
            endpoint=_LEAGUES_ENDPOINT,
            parameters=(("id", str(league_id)),),
        )
        http_request = HttpRequestIdentity(logical_request=logical_request)
        request_parameters = {"id": str(league_id)}

        requested_at = _utc_now()
        try:
            response = self._client.get(_LEAGUES_ENDPOINT, params=request_parameters)
        except httpx.HTTPError as exc:
            raise ApiFootballError(f"transport failure calling {_LEAGUES_ENDPOINT}") from exc

        raw_body = response.content
        received_at = _utc_now()
        raw_content = RawContent(body=raw_body)

        observation = RawObservation(
            provider=PROVIDER_NAME,
            endpoint=_LEAGUES_ENDPOINT,
            logical_request=logical_request,
            http_request=http_request,
            request_parameters=request_parameters,
            requested_at=requested_at,
            received_at=received_at,
            http_status=response.status_code,
            job_run_id=job_run_id,
            raw_content=raw_content,
        )

        if not response.is_success:
            raise ApiFootballHttpError(response.status_code, observation=observation)

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ApiFootballMalformedResponseError("response body is not valid JSON", observation=observation) from exc

        payload = _validate_envelope_shape(payload, observation)

        if len(payload["errors"]) > 0:
            raise ApiFootballProviderError(payload["errors"], observation=observation)

        response_list = payload["response"]
        if len(response_list) == 0:
            return LeagueFetchResult(observation=observation, league=None)
        if len(response_list) > 1:
            # 0.5.1F fix 3: a single-id lookup (?id=<league_id>) has valid
            # cardinality 0 or 1; more than one entry means the provider
            # response no longer matches what this endpoint method
            # promises to callers. The already-constructed observation
            # (exact raw bytes/fingerprint included) is preserved on the
            # exception exactly like every other malformed-response path.
            raise ApiFootballMalformedResponseError(
                f"expected at most one league for a single id lookup, got {len(response_list)}",
                observation=observation,
            )

        league = _parse_league(response_list[0], observation)
        return LeagueFetchResult(observation=observation, league=league)
