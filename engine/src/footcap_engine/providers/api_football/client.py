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
    ApiFootballFixture,
    ApiFootballHttpError,
    ApiFootballLeague,
    ApiFootballMalformedResponseError,
    ApiFootballProviderError,
    ApiFootballTeam,
    FixturesFetchResult,
    HttpRequestIdentity,
    LeagueFetchResult,
    LogicalRequestIdentity,
    RawContent,
    RawObservation,
    TeamsFetchResult,
)

_LEAGUES_ENDPOINT = "/leagues"
_TEAMS_ENDPOINT = "/teams"
_FIXTURES_ENDPOINT = "/fixtures"
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


def _require_dict(container: dict, key: str, observation: RawObservation, path: str) -> dict:
    if key not in container:
        raise ApiFootballMalformedResponseError(f"{path} is missing", observation=observation)
    value = container[key]
    if not isinstance(value, dict):
        raise ApiFootballMalformedResponseError(f"{path} must be an object, got {type(value)!r}", observation=observation)
    return value


def _require_key(container: dict, key: str, observation: RawObservation, path: str) -> object:
    if key not in container:
        raise ApiFootballMalformedResponseError(f"{path} is missing", observation=observation)
    return container[key]


def _parse_kickoff_at(fixture_obj: dict, observation: RawObservation) -> tuple[datetime, str]:
    """Derives kickoff_at from fixture.timestamp (Unix seconds, the
    canonical source) and cross-validates it against fixture.date
    (ISO 8601 with required UTC offset) by comparing instants, not
    text -- two representations of the same instant with different
    offsets are accepted; a genuine disagreement is malformed data,
    never silently resolved by preferring one field over the other."""
    timestamp = _require_key(fixture_obj, "timestamp", observation, "fixture.timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise ApiFootballMalformedResponseError(
            f"fixture.timestamp must be an int, got {type(timestamp)!r}", observation=observation
        )
    # A structurally valid int can still be outside the platform/Python
    # datetime representable range. datetime.fromtimestamp() can raise
    # OverflowError, OSError, or ValueError depending on platform and
    # magnitude (observed: OSError for moderately out-of-range values,
    # OverflowError for extreme ones) -- an HTTP response already exists
    # here, so none of these may escape uncaught.
    try:
        kickoff_from_timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ApiFootballMalformedResponseError(
            f"fixture.timestamp is invalid or outside the supported datetime range: {timestamp!r}",
            observation=observation,
        ) from exc

    date_value = _require_key(fixture_obj, "date", observation, "fixture.date")
    if not isinstance(date_value, str) or not date_value.strip():
        raise ApiFootballMalformedResponseError("fixture.date must be a non-blank string", observation=observation)
    try:
        parsed_date = datetime.fromisoformat(date_value)
    except ValueError as exc:
        raise ApiFootballMalformedResponseError(
            f"fixture.date is not valid ISO 8601: {date_value!r}", observation=observation
        ) from exc
    if parsed_date.tzinfo is None or parsed_date.utcoffset() is None:
        raise ApiFootballMalformedResponseError(
            "fixture.date must contain UTC offset information", observation=observation
        )
    # An offset-aware datetime near datetime.min/max can parse
    # successfully but overflow while shifting to UTC (e.g.
    # 9999-12-31T23:59:59-14:00 normalizes past year 9999).
    try:
        kickoff_from_date = parsed_date.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ApiFootballMalformedResponseError(
            f"fixture.date is outside the supported datetime range when normalized to UTC: {date_value!r}",
            observation=observation,
        ) from exc

    if kickoff_from_date != kickoff_from_timestamp:
        raise ApiFootballMalformedResponseError(
            "fixture.timestamp and fixture.date do not represent the same instant", observation=observation
        )

    timezone_value = _require_key(fixture_obj, "timezone", observation, "fixture.timezone")
    if not isinstance(timezone_value, str) or not timezone_value.strip():
        raise ApiFootballMalformedResponseError("fixture.timezone must be a non-blank string", observation=observation)

    return kickoff_from_timestamp, timezone_value


def _parse_fixture(
    entry: object, requested_league_id: int, requested_season: int, observation: RawObservation
) -> ApiFootballFixture:
    if not isinstance(entry, dict):
        raise ApiFootballMalformedResponseError("response entry is not an object", observation=observation)

    fixture_obj = _require_dict(entry, "fixture", observation, "fixture")
    league_obj = _require_dict(entry, "league", observation, "league")
    teams_obj = _require_dict(entry, "teams", observation, "teams")
    goals_obj = _require_dict(entry, "goals", observation, "goals")

    kickoff_at, provider_timezone = _parse_kickoff_at(fixture_obj, observation)

    status_obj = _require_dict(fixture_obj, "status", observation, "fixture.status")
    home_obj = _require_dict(teams_obj, "home", observation, "teams.home")
    away_obj = _require_dict(teams_obj, "away", observation, "teams.away")

    try:
        fixture = ApiFootballFixture(
            provider_fixture_id=_require_key(fixture_obj, "id", observation, "fixture.id"),
            provider_league_id=_require_key(league_obj, "id", observation, "league.id"),
            season=_require_key(league_obj, "season", observation, "league.season"),
            round=_require_key(league_obj, "round", observation, "league.round"),
            kickoff_at=kickoff_at,
            provider_timezone=provider_timezone,
            provider_status_short=_require_key(status_obj, "short", observation, "fixture.status.short"),
            provider_status_long=_require_key(status_obj, "long", observation, "fixture.status.long"),
            provider_status_elapsed=_require_key(status_obj, "elapsed", observation, "fixture.status.elapsed"),
            home_provider_team_id=_require_key(home_obj, "id", observation, "teams.home.id"),
            away_provider_team_id=_require_key(away_obj, "id", observation, "teams.away.id"),
            home_goals=_require_key(goals_obj, "home", observation, "goals.home"),
            away_goals=_require_key(goals_obj, "away", observation, "goals.away"),
        )
    except ApiFootballMalformedResponseError as exc:
        raise ApiFootballMalformedResponseError(str(exc), observation=observation) from exc

    # Request-context consistency: ApiFootballFixture itself does not
    # know the original request (see models.py), so this comparison
    # lives here, after the DTO's own field constraints already passed.
    if fixture.provider_league_id != requested_league_id:
        raise ApiFootballMalformedResponseError(
            f"league.id {fixture.provider_league_id} does not match requested league_id {requested_league_id}",
            observation=observation,
        )
    if fixture.season != requested_season:
        raise ApiFootballMalformedResponseError(
            f"league.season {fixture.season} does not match requested season {requested_season}",
            observation=observation,
        )

    return fixture


def _parse_fixtures(
    response_list: list, requested_league_id: int, requested_season: int, observation: RawObservation
) -> tuple[ApiFootballFixture, ...]:
    """Parses every entry, preserving provider order exactly. A set is
    used only as an auxiliary O(1) membership check for duplicate
    detection -- it never determines output order or content, so it
    cannot silently reorder or drop anything; the first duplicate found
    raises immediately with the observation preserved."""
    fixtures: list[ApiFootballFixture] = []
    seen_ids: set[int] = set()
    for entry in response_list:
        fixture = _parse_fixture(entry, requested_league_id, requested_season, observation)
        if fixture.provider_fixture_id in seen_ids:
            raise ApiFootballMalformedResponseError(
                f"duplicate fixture id {fixture.provider_fixture_id} in response", observation=observation
            )
        seen_ids.add(fixture.provider_fixture_id)
        fixtures.append(fixture)
    return tuple(fixtures)


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

    def get_fixtures(self, league_id: int, season: int, job_run_id: str) -> FixturesFetchResult:
        """GET /fixtures?league=<league_id>&season=<season>. Returns a
        FixturesFetchResult whose `observation` is always populated for
        any successfully received HTTP response (ADR-011); `fixtures` is
        an empty tuple only for a valid, empty provider response list.
        This method does not implement pagination traversal: if the
        provider reports more than one page, it raises rather than
        silently returning page 1 as though it were the complete
        season."""
        league_id = _validate_league_id(league_id)
        season = _validate_season(season)
        job_run_id = _validate_job_run_id(job_run_id)

        logical_request = LogicalRequestIdentity(
            provider=PROVIDER_NAME,
            endpoint=_FIXTURES_ENDPOINT,
            parameters=(("league", str(league_id)), ("season", str(season))),
        )
        http_request = HttpRequestIdentity(logical_request=logical_request)
        request_parameters = {"league": str(league_id), "season": str(season)}

        requested_at = _utc_now()
        try:
            response = self._client.get(_FIXTURES_ENDPOINT, params=request_parameters)
        except httpx.HTTPError as exc:
            raise ApiFootballError(f"transport failure calling {_FIXTURES_ENDPOINT}") from exc

        raw_body = response.content
        received_at = _utc_now()
        raw_content = RawContent(body=raw_body)

        observation = RawObservation(
            provider=PROVIDER_NAME,
            endpoint=_FIXTURES_ENDPOINT,
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

        fixtures = _parse_fixtures(payload["response"], league_id, season, observation)
        return FixturesFetchResult(observation=observation, fixtures=fixtures)
