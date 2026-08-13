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
    ApiFootballTeam,
    HttpRequestIdentity,
    LeagueFetchResult,
    LogicalRequestIdentity,
    RawContent,
    RawObservation,
    TeamsFetchResult,
)

_LEAGUES_ENDPOINT = "/leagues"
_TEAMS_ENDPOINT = "/teams"
_ENVELOPE_KEYS = ("get", "parameters", "errors", "results", "paging", "response")
_TEAM_KEYS = ("id", "name", "code", "country", "founded", "national", "logo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_league_id(league_id: object) -> int:
    if isinstance(league_id, bool) or not isinstance(league_id, int):
        raise ApiFootballError(f"league_id must be an int, got {type(league_id)!r}")
    if league_id <= 0:
        raise ApiFootballError("league_id must be a positive integer")
    return league_id


def _validate_season(season: object) -> int:
    if isinstance(season, bool) or not isinstance(season, int):
        raise ApiFootballError(f"season must be an int, got {type(season)!r}")
    if not (1000 <= season <= 9999):
        raise ApiFootballError("season must be a four-digit year (1000-9999)")
    return season


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


def _validate_single_page(payload: dict, observation: RawObservation) -> None:
    """get_teams() does not implement pagination traversal (out of scope
    for this slice, per ADR-011's deferral of pagination architecture).
    A response is representable as a complete result only when
    paging.current == 1 and paging.total == 1 -- both present, both
    plain ints (bool rejected), both exactly 1. Anything else (missing,
    wrong type, zero, negative, or genuinely multi-page) is rejected
    rather than silently returned as if page 1 were the whole result."""
    paging = payload.get("paging")
    if not isinstance(paging, dict):
        raise ApiFootballMalformedResponseError("envelope 'paging' field is missing or malformed", observation=observation)
    for field_name in ("current", "total"):
        if field_name not in paging:
            raise ApiFootballMalformedResponseError(
                f"envelope 'paging.{field_name}' is missing", observation=observation
            )
        value = paging[field_name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ApiFootballMalformedResponseError(
                f"envelope 'paging.{field_name}' must be an int, got {type(value)!r}", observation=observation
            )
        if value != 1:
            raise ApiFootballMalformedResponseError(
                f"provider response is not a single complete page (paging.{field_name}={value}); "
                "get_teams() does not implement pagination traversal",
                observation=observation,
            )


def _parse_team(entry: object, observation: RawObservation) -> ApiFootballTeam:
    if not isinstance(entry, dict):
        raise ApiFootballMalformedResponseError("response entry is not an object", observation=observation)
    team_obj = entry.get("team")
    if not isinstance(team_obj, dict):
        raise ApiFootballMalformedResponseError("response entry.team is missing or not an object", observation=observation)

    missing = [key for key in _TEAM_KEYS if key not in team_obj]
    if missing:
        raise ApiFootballMalformedResponseError(
            f"team object missing required key(s): {', '.join(missing)}", observation=observation
        )

    try:
        return ApiFootballTeam(
            provider_team_id=team_obj["id"],
            name=team_obj["name"],
            code=team_obj["code"],
            country=team_obj["country"],
            founded=team_obj["founded"],
            national=team_obj["national"],
            logo=team_obj["logo"],
        )
    except ApiFootballMalformedResponseError as exc:
        raise ApiFootballMalformedResponseError(str(exc), observation=observation) from exc


def _parse_teams(response_list: list, observation: RawObservation) -> tuple[ApiFootballTeam, ...]:
    """Parses every entry, preserving provider order exactly. A set is
    used only as an auxiliary O(1) membership check for duplicate
    detection -- it never determines output order or content, so it
    cannot silently reorder or drop anything; the first duplicate found
    raises immediately with the observation preserved."""
    teams: list[ApiFootballTeam] = []
    seen_ids: set[int] = set()
    for entry in response_list:
        team = _parse_team(entry, observation)
        if team.provider_team_id in seen_ids:
            raise ApiFootballMalformedResponseError(
                f"duplicate team id {team.provider_team_id} in response", observation=observation
            )
        seen_ids.add(team.provider_team_id)
        teams.append(team)
    return tuple(teams)


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
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # json.loads(bytes) can fail two distinct ways: the bytes
            # don't decode as text at all (UnicodeDecodeError, raised
            # before any JSON parsing is attempted) or they decode but
            # aren't valid JSON (json.JSONDecodeError). Neither is a
            # subclass of the other -- both are ValueError siblings --
            # so both must be caught explicitly or a malformed-encoding
            # response would escape without the RawObservation attached.
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

    def get_teams(self, league_id: int, season: int, job_run_id: str) -> TeamsFetchResult:
        """GET /teams?league=<league_id>&season=<season>. Returns a
        TeamsFetchResult whose `observation` is always populated for any
        successfully received HTTP response (ADR-011); `teams` is an
        empty tuple only for a valid, empty provider response list. This
        method does not implement pagination traversal: if the provider
        reports more than one page, it raises rather than silently
        returning page 1 as though it were the complete result."""
        league_id = _validate_league_id(league_id)
        season = _validate_season(season)
        job_run_id = _validate_job_run_id(job_run_id)

        logical_request = LogicalRequestIdentity(
            provider=PROVIDER_NAME,
            endpoint=_TEAMS_ENDPOINT,
            parameters=(("league", str(league_id)), ("season", str(season))),
        )
        http_request = HttpRequestIdentity(logical_request=logical_request)
        request_parameters = {"league": str(league_id), "season": str(season)}

        requested_at = _utc_now()
        try:
            response = self._client.get(_TEAMS_ENDPOINT, params=request_parameters)
        except httpx.HTTPError as exc:
            raise ApiFootballError(f"transport failure calling {_TEAMS_ENDPOINT}") from exc

        raw_body = response.content
        received_at = _utc_now()
        raw_content = RawContent(body=raw_body)

        observation = RawObservation(
            provider=PROVIDER_NAME,
            endpoint=_TEAMS_ENDPOINT,
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
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # json.loads(bytes) can fail two distinct ways: the bytes
            # don't decode as text at all (UnicodeDecodeError, raised
            # before any JSON parsing is attempted) or they decode but
            # aren't valid JSON (json.JSONDecodeError). Neither is a
            # subclass of the other -- both are ValueError siblings --
            # so both must be caught explicitly or a malformed-encoding
            # response would escape without the RawObservation attached.
            raise ApiFootballMalformedResponseError("response body is not valid JSON", observation=observation) from exc

        payload = _validate_envelope_shape(payload, observation)

        if len(payload["errors"]) > 0:
            raise ApiFootballProviderError(payload["errors"], observation=observation)

        _validate_single_page(payload, observation)

        teams = _parse_teams(payload["response"], observation)
        return TeamsFetchResult(observation=observation, teams=teams)
