"""
httpx.MockTransport-based integration tests for ApiFootballClient. No
unit test in this file requires internet access -- every request is
served by an in-process MockTransport handler.

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath.
"""
import dataclasses
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import httpx
import pytest

from footcap_engine.providers.api_football import (
    ApiFootballClient,
    ApiFootballConfig,
    ApiFootballError,
    ApiFootballHttpError,
    ApiFootballMalformedResponseError,
    ApiFootballProviderError,
)

_TEAMS_KEYS = ("id", "name", "code", "country", "founded", "national", "logo")

API_KEY = "test-fake-key-do-not-use"


def _valid_envelope(response: list) -> bytes:
    return json.dumps(
        {
            "get": "leagues",
            "parameters": {"id": "135"},
            "errors": [],
            "results": len(response),
            "paging": {"current": 1, "total": 1},
            "response": response,
        }
    ).encode("utf-8")


VALID_LEAGUE_ENTRY = {
    "league": {"id": 135, "name": "Serie A", "type": "League", "logo": "https://example.test/logo.png"},
    "country": {"name": "Italy", "code": "IT", "flag": "https://example.test/flag.png"},
}


def _client(handler, *, api_key: str = API_KEY) -> ApiFootballClient:
    config = ApiFootballConfig(api_key=api_key)
    transport = httpx.MockTransport(handler)
    return ApiFootballClient(config, transport=transport)


def _handler_returning(status: int, body: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return handler


# ==== REQUEST INPUT (matrix items 5-9) ====

def test_valid_league_id_accepted():
    client = _client(_handler_returning(200, _valid_envelope([VALID_LEAGUE_ENTRY])))
    result = client.get_league(135, job_run_id="job-1")
    assert result.league.provider_league_id == 135


def test_zero_league_id_rejected():
    client = _client(_handler_returning(200, _valid_envelope([])))
    with pytest.raises(ApiFootballError):
        client.get_league(0, job_run_id="job-1")


def test_negative_league_id_rejected():
    client = _client(_handler_returning(200, _valid_envelope([])))
    with pytest.raises(ApiFootballError):
        client.get_league(-135, job_run_id="job-1")


def test_bool_league_id_rejected():
    client = _client(_handler_returning(200, _valid_envelope([])))
    with pytest.raises(ApiFootballError):
        client.get_league(True, job_run_id="job-1")


def test_blank_job_run_id_rejected():
    client = _client(_handler_returning(200, _valid_envelope([])))
    with pytest.raises(ApiFootballError):
        client.get_league(135, job_run_id="   ")


# ==== TRANSPORT / AUTH (matrix items 10-12) ====

def test_request_uses_direct_documented_base_host():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        return httpx.Response(200, content=_valid_envelope([]))

    client = _client(handler)
    client.get_league(135, job_run_id="job-1")
    assert seen["host"] == "v3.football.api-sports.io"
    assert seen["path"] == "/leagues"


def test_auth_header_is_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("x-apisports-key")
        return httpx.Response(200, content=_valid_envelope([]))

    client = _client(handler, api_key=API_KEY)
    client.get_league(135, job_run_id="job-1")
    assert seen["header"] == API_KEY


def test_transport_is_injectable_and_offline():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, content=_valid_envelope([VALID_LEAGUE_ENTRY]))

    client = _client(handler)
    client.get_league(135, job_run_id="job-1")
    assert calls["count"] == 1  # proves the mock transport, not the network, served the request


# ==== RAW-BYTE / FINGERPRINT VALIDATION (matrix item 15, section 21) ====

def test_fingerprint_matches_exact_mocked_response_bytes_not_reserialized_json():
    # Deliberately unusual whitespace/key order so a naive
    # parse-then-reserialize implementation would produce different bytes.
    exact_bytes = (
        b'{"get":"leagues","parameters":{"id":"135"},"errors":[],"results":1,'
        b'"paging":{"current":1,   "total":1},'
        b'"response":[{"league":{"id":135,"name":"Serie A","type":"League","logo":null},'
        b'"country":{"name":"Italy"}}]}'
    )
    client = _client(_handler_returning(200, exact_bytes))
    result = client.get_league(135, job_run_id="job-1")

    assert result.observation.raw_content.body == exact_bytes
    assert result.observation.raw_content.content_fingerprint == hashlib.sha256(exact_bytes).hexdigest()

    reserialized = json.dumps(json.loads(exact_bytes)).encode("utf-8")
    assert reserialized != exact_bytes
    assert hashlib.sha256(reserialized).hexdigest() != result.observation.raw_content.content_fingerprint


def test_two_calls_with_identical_bodies_produce_distinct_observations_with_same_fingerprint():
    body = _valid_envelope([VALID_LEAGUE_ENTRY])
    client = _client(_handler_returning(200, body))

    first = client.get_league(135, job_run_id="job-1")
    second = client.get_league(135, job_run_id="job-1")

    assert first.observation is not second.observation  # distinct occurrences (ADR-011 decision 7)
    assert first.observation.raw_content.content_fingerprint == second.observation.raw_content.content_fingerprint


def test_request_parameters_contain_league_id_but_no_credential():
    client = _client(_handler_returning(200, _valid_envelope([VALID_LEAGUE_ENTRY])))
    result = client.get_league(135, job_run_id="job-1")
    assert dict(result.observation.request_parameters) == {"id": "135"}
    assert API_KEY not in result.observation.request_parameters.values()


# ==== ENVELOPE (matrix items 26-31) ====

def test_valid_league_response_parses():
    client = _client(_handler_returning(200, _valid_envelope([VALID_LEAGUE_ENTRY])))
    result = client.get_league(135, job_run_id="job-1")
    assert result.league.provider_league_id == 135
    assert result.league.name == "Serie A"
    assert result.league.country_name == "Italy"


def test_valid_empty_response_returns_league_none():
    client = _client(_handler_returning(200, _valid_envelope([])))
    result = client.get_league(135, job_run_id="job-1")
    assert result.league is None
    assert result.observation is not None  # raw provenance retained even when empty (ADR-011)


def test_malformed_json_rejected():
    client = _client(_handler_returning(200, b"not json at all {"))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.observation is not None  # raw bytes retained even on malformed response


def test_malformed_envelope_rejected():
    body = json.dumps({"get": "leagues"}).encode("utf-8")  # missing errors/results/paging/response
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_provider_declared_errors_rejected():
    body = json.dumps(
        {
            "get": "leagues",
            "parameters": {"id": "135"},
            "errors": {"id": "Invalid league id"},
            "results": 0,
            "paging": {"current": 1, "total": 1},
            "response": [],
        }
    ).encode("utf-8")
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballProviderError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.provider_errors == {"id": "Invalid league id"}


def test_http_non_success_rejected():
    client = _client(_handler_returning(403, b'{"message": "Forbidden"}'))
    with pytest.raises(ApiFootballHttpError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.status_code == 403
    assert excinfo.value.observation is not None  # raw bytes retained even on HTTP error (ADR-011 section 14)


# ==== 0.5.1F FIX 3: single-id league response cardinality ====
# Cardinality 0 and 1 are already covered by
# test_valid_empty_response_returns_league_none (matrix item 11) and
# test_valid_league_response_parses (matrix item 12) above; only the
# new >1 behavior (matrix items 13-15) is added here.

def test_multiple_leagues_in_response_rejected():
    body = _valid_envelope([VALID_LEAGUE_ENTRY, VALID_LEAGUE_ENTRY])
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert "2" in str(excinfo.value)


def test_multiple_leagues_rejection_retains_raw_observation():
    body = _valid_envelope([VALID_LEAGUE_ENTRY, VALID_LEAGUE_ENTRY])
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.http_status == 200


def test_multiple_leagues_rejection_retains_exact_raw_body_and_fingerprint():
    body = _valid_envelope([VALID_LEAGUE_ENTRY, VALID_LEAGUE_ENTRY])
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.observation.raw_content.body == body
    assert excinfo.value.observation.raw_content.content_fingerprint == hashlib.sha256(body).hexdigest()


# ==== SECRET SAFETY (matrix items 35-36) ====

def test_exception_text_never_exposes_api_key():
    client = _client(_handler_returning(403, b'{"message": "Forbidden"}'), api_key="super-secret-do-not-leak")
    with pytest.raises(ApiFootballHttpError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert "super-secret-do-not-leak" not in str(excinfo.value)

    body = json.dumps({"get": "leagues", "parameters": {}, "errors": ["bad key"], "results": 0, "paging": {}, "response": []}).encode()
    client2 = _client(_handler_returning(200, body), api_key="super-secret-do-not-leak")
    with pytest.raises(ApiFootballProviderError) as excinfo2:
        client2.get_league(135, job_run_id="job-1")
    assert "super-secret-do-not-leak" not in str(excinfo2.value)


def test_observation_never_contains_auth_header_or_key():
    client = _client(_handler_returning(200, _valid_envelope([VALID_LEAGUE_ENTRY])), api_key="super-secret-do-not-leak")
    result = client.get_league(135, job_run_id="job-1")

    observation = result.observation
    assert not hasattr(observation, "headers")
    assert "super-secret-do-not-leak" not in repr(observation)
    assert "super-secret-do-not-leak" not in observation.request_parameters.values()
    assert "super-secret-do-not-leak" not in repr(observation.logical_request)
    assert "super-secret-do-not-leak" not in repr(observation.http_request)


# =====================================================================
# TEAMS (0.5.3B) -- GET /teams?league=<id>&season=<year>
# =====================================================================

def _valid_teams_envelope(response: list, paging_total: int = 1) -> bytes:
    return json.dumps(
        {
            "get": "teams",
            "parameters": {"league": "135", "season": "2023"},
            "errors": [],
            "results": len(response),
            "paging": {"current": 1, "total": paging_total},
            "response": response,
        }
    ).encode("utf-8")


def _team_entry(**overrides) -> dict:
    team = {
        "id": 505,
        "name": "Inter",
        "code": "INT",
        "country": "Italy",
        "founded": 1908,
        "national": False,
        "logo": "https://example.test/teams/505.png",
    }
    team.update(overrides)
    return {
        "team": team,
        "venue": {"id": 907, "name": "Giuseppe Meazza", "city": "Milano", "capacity": 75923, "surface": "grass"},
    }


VALID_TEAM_ENTRY = _team_entry()
SECOND_VALID_TEAM_ENTRY = _team_entry(id=506, name="Milan", code="MIL")


# ==== INPUT (matrix items 1-8) ====

def test_teams_valid_league_and_season_accepted():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert result.teams[0].provider_team_id == 505


def _handler_that_must_not_be_called(request: httpx.Request) -> httpx.Response:
    # A "rejected before HTTP" test is only meaningful if the transport
    # genuinely was never reached. Failing loudly from inside the
    # handler proves that, rather than merely asserting that some
    # ApiFootballError eventually surfaced.
    pytest.fail("transport handler must not be invoked for input rejected before HTTP")


@pytest.mark.parametrize("league_id", [True, 0, -135, "135"])
def test_teams_invalid_league_id_rejected_before_http(league_id):
    client = _client(_handler_that_must_not_be_called)
    with pytest.raises(ApiFootballError):
        client.get_teams(league_id, 2023, job_run_id="job-1")


@pytest.mark.parametrize("season", [True, 999, 10000, "2023"])
def test_teams_invalid_season_rejected_before_http(season):
    client = _client(_handler_that_must_not_be_called)
    with pytest.raises(ApiFootballError):
        client.get_teams(135, season, job_run_id="job-1")


@pytest.mark.parametrize("job_run_id", ["", "   ", 123])
def test_teams_invalid_job_run_id_rejected_before_http(job_run_id):
    client = _client(_handler_that_must_not_be_called)
    with pytest.raises(ApiFootballError):
        client.get_teams(135, 2023, job_run_id=job_run_id)


# ==== REQUEST (matrix items 9-15) ====

def test_teams_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["league"] = request.url.params.get("league")
        seen["season"] = request.url.params.get("season")
        seen["auth"] = request.headers.get("x-apisports-key")
        return httpx.Response(200, content=_valid_teams_envelope([VALID_TEAM_ENTRY]))

    client = _client(handler, api_key=API_KEY)
    client.get_teams(135, 2023, job_run_id="job-1")
    assert seen["host"] == "v3.football.api-sports.io"
    assert seen["path"] == "/teams"
    assert seen["league"] == "135"
    assert seen["season"] == "2023"
    assert seen["auth"] == API_KEY


def test_teams_logical_identity_contains_league_and_season_but_not_credentials_or_job_run_id():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])), api_key="key-one")
    first = client.get_teams(135, 2023, job_run_id="job-1")

    client2 = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])), api_key="key-two")
    second = client2.get_teams(135, 2023, job_run_id="job-2")

    assert dict(first.observation.logical_request.parameters) == {"league": "135", "season": "2023"}
    assert first.observation.logical_request == second.observation.logical_request
    assert "key-one" not in repr(first.observation.logical_request)
    assert "job-1" not in repr(first.observation.logical_request)


# ==== RAW PROVENANCE (matrix items 16-20) ====

def test_teams_exact_bytes_and_fingerprint_retained():
    exact_bytes = (
        b'{"get":"teams","parameters":{"league":"135",   "season":"2023"},"errors":[],"results":1,'
        b'"paging":{"current":1,"total":1},'
        b'"response":[{"team":{"id":505,"name":"Inter","code":"INT","country":"Italy",'
        b'"founded":1908,"national":false,"logo":null},"venue":{"id":907}}]}'
    )
    client = _client(_handler_returning(200, exact_bytes))
    result = client.get_teams(135, 2023, job_run_id="job-1")

    assert result.observation.raw_content.body == exact_bytes
    assert result.observation.raw_content.content_fingerprint == hashlib.sha256(exact_bytes).hexdigest()

    reserialized = json.dumps(json.loads(exact_bytes)).encode("utf-8")
    assert reserialized != exact_bytes
    assert hashlib.sha256(reserialized).hexdigest() != result.observation.raw_content.content_fingerprint


def test_teams_raw_observation_request_parameters_match_league_and_season():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert dict(result.observation.request_parameters) == {"league": "135", "season": "2023"}
    assert API_KEY not in result.observation.request_parameters.values()


def test_teams_timestamps_are_utc():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert result.observation.requested_at.tzinfo is not None
    assert result.observation.received_at.tzinfo is not None
    assert result.observation.received_at >= result.observation.requested_at


def test_observation_retained_on_malformed_team_response():
    bad_entry = _team_entry()
    del bad_entry["team"]["logo"]
    client = _client(_handler_returning(200, _valid_teams_envelope([bad_entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.http_status == 200


# ==== ENVELOPE / HTTP (matrix items 21-27) ====

def test_teams_valid_nonempty_response_accepted():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert isinstance(result.teams, tuple)
    assert len(result.teams) == 1


def test_teams_valid_empty_response_returns_empty_tuple():
    client = _client(_handler_returning(200, _valid_teams_envelope([])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert result.teams == ()
    assert result.observation is not None


def test_teams_malformed_json_rejected():
    client = _client(_handler_returning(200, b"not json at all {"))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_teams_malformed_envelope_rejected():
    body = json.dumps({"get": "teams"}).encode("utf-8")
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_teams_provider_errors_rejected():
    body = json.dumps(
        {
            "get": "teams",
            "parameters": {"league": "135", "season": "2023"},
            "errors": {"season": "Invalid season"},
            "results": 0,
            "paging": {"current": 1, "total": 1},
            "response": [],
        }
    ).encode("utf-8")
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballProviderError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.provider_errors == {"season": "Invalid season"}


def test_teams_http_non_success_rejected():
    client = _client(_handler_returning(500, b"internal error"))
    with pytest.raises(ApiFootballHttpError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.status_code == 500
    assert excinfo.value.observation is not None


def test_teams_single_complete_page_accepted():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert result.teams[0].provider_team_id == 505


def _teams_envelope_with_paging(response: list, paging: dict) -> bytes:
    return json.dumps(
        {
            "get": "teams",
            "parameters": {"league": "135", "season": "2023"},
            "errors": [],
            "results": len(response),
            "paging": paging,
            "response": response,
        }
    ).encode("utf-8")


@pytest.mark.parametrize(
    "paging",
    [
        {"total": 1},  # current missing
        {"current": True, "total": 1},
        {"current": "1", "total": 1},
        {"current": 0, "total": 1},
        {"current": -1, "total": 1},
        {"current": 2, "total": 1},
        {"current": 1},  # total missing
        {"current": 1, "total": True},
        {"current": 1, "total": "1"},
        {"current": 1, "total": 0},
        {"current": 1, "total": -1},
        {"current": 1, "total": 2},
    ],
)
def test_teams_invalid_paging_state_rejected(paging):
    body = _teams_envelope_with_paging([VALID_TEAM_ENTRY], paging)
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == body


# ==== FIX 1: json.loads(bytes) can raise UnicodeDecodeError, not only
# json.JSONDecodeError -- both must retain RawObservation. Verified for
# both get_teams() and get_league(), since both share the same
# malformed-decode handling pattern. ====

INVALID_UTF16_BYTES = b"\xff\xfe\xfd"  # not valid JSON and not decodable text


def test_teams_invalidly_encoded_bytes_rejected_with_observation_retained():
    client = _client(_handler_returning(200, INVALID_UTF16_BYTES))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == INVALID_UTF16_BYTES


def test_league_invalidly_encoded_bytes_rejected_with_observation_retained():
    client = _client(_handler_returning(200, INVALID_UTF16_BYTES))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_league(135, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == INVALID_UTF16_BYTES


# ==== DTO (matrix items 28-38) ====

def test_teams_dto_full_fields_retained():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    team = client.get_teams(135, 2023, job_run_id="job-1").teams[0]
    assert team.provider_team_id == 505
    assert team.name == "Inter"
    assert team.code == "INT"
    assert team.country == "Italy"
    assert team.founded == 1908
    assert team.national is False
    assert team.logo == "https://example.test/teams/505.png"


def test_teams_dto_nullable_fields_accept_null():
    entry = _team_entry(code=None, country=None, founded=None, logo=None)
    client = _client(_handler_returning(200, _valid_teams_envelope([entry])))
    team = client.get_teams(135, 2023, job_run_id="job-1").teams[0]
    assert team.code is None
    assert team.country is None
    assert team.founded is None
    assert team.logo is None
    assert team.national is False  # not nullable; still correctly populated


# ==== STRUCTURAL KEY PRESENCE (matrix items 39-45) ====

@pytest.mark.parametrize("missing_key", _TEAMS_KEYS)
def test_teams_missing_required_key_rejected(missing_key):
    entry = _team_entry()
    del entry["team"][missing_key]
    client = _client(_handler_returning(200, _valid_teams_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert missing_key in str(excinfo.value)


# ==== COLLECTION (matrix items 55-59) ====

def test_teams_provider_order_preserved():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY, SECOND_VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    assert [team.provider_team_id for team in result.teams] == [505, 506]


def test_teams_duplicate_provider_team_ids_rejected():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY, VALID_TEAM_ENTRY])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert "505" in str(excinfo.value)
    assert excinfo.value.observation is not None


def test_teams_malformed_second_entry_fails_whole_result_no_partial_return():
    bad_entry = _team_entry(id=506)
    del bad_entry["team"]["code"]
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY, bad_entry, VALID_TEAM_ENTRY])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_teams(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None  # nothing about a partial TeamsFetchResult is ever returned


# ==== BOUNDARIES (matrix items 60-64) ====

def test_teams_venue_ignored_at_dto_level_but_present_in_raw_bytes():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")

    team = result.teams[0]
    assert not hasattr(team, "venue")
    assert {f.name for f in dataclasses.fields(team)} == {
        "provider_team_id",
        "name",
        "code",
        "country",
        "founded",
        "national",
        "logo",
    }
    # exact venue bytes remain fully recoverable from the raw response
    assert b'"venue"' in result.observation.raw_content.body
    assert b'"Giuseppe Meazza"' in result.observation.raw_content.body


def test_teams_dto_never_carries_league_season_or_footcap_identity():
    client = _client(_handler_returning(200, _valid_teams_envelope([VALID_TEAM_ENTRY])))
    result = client.get_teams(135, 2023, job_run_id="job-1")
    team_fields = {f.name for f in dataclasses.fields(result.teams[0])}
    result_fields = {f.name for f in dataclasses.fields(result)}
    assert "league_id" not in team_fields and "season" not in team_fields
    assert "league_id" not in result_fields and "season" not in result_fields
    assert not any("team_id" == name or "footcap" in name.lower() for name in team_fields)


# =====================================================================
# FIXTURES (0.5.4B) -- GET /fixtures?league=<id>&season=<year>
# =====================================================================

# 2026-08-13T20:00:00+02:00 and 2026-08-13T18:00:00Z are the same instant.
KICKOFF_TIMESTAMP = 1786644000
KICKOFF_DATE = "2026-08-13T20:00:00+02:00"
KICKOFF_UTC = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)


def _valid_fixtures_envelope(response: list, current: int = 1, total: int = 1) -> bytes:
    return json.dumps(
        {
            "get": "fixtures",
            "parameters": {"league": "135", "season": "2023"},
            "errors": [],
            "results": len(response),
            "paging": {"current": current, "total": total},
            "response": response,
        }
    ).encode("utf-8")


def _fixture_entry(
    *,
    fixture_id=555,
    timestamp=KICKOFF_TIMESTAMP,
    date=KICKOFF_DATE,
    tz="UTC",
    status_short="NS",
    status_long="Not Started",
    elapsed=None,
    league_id=135,
    season=2023,
    round_="Regular Season - 1",
    home_id=505,
    away_id=506,
    home_goals=None,
    away_goals=None,
) -> dict:
    return {
        "fixture": {
            "id": fixture_id,
            "timestamp": timestamp,
            "date": date,
            "timezone": tz,
            "status": {"short": status_short, "long": status_long, "elapsed": elapsed},
        },
        "league": {"id": league_id, "season": season, "round": round_},
        "teams": {"home": {"id": home_id}, "away": {"id": away_id}},
        "goals": {"home": home_goals, "away": away_goals},
    }


VALID_FIXTURE_ENTRY = _fixture_entry()
SECOND_VALID_FIXTURE_ENTRY = _fixture_entry(fixture_id=556, home_id=507, away_id=508)
THIRD_VALID_FIXTURE_ENTRY = _fixture_entry(fixture_id=557, home_id=509, away_id=510)


def _delete_path(entry: dict, path: str) -> dict:
    parts = path.split(".")
    target = entry
    for part in parts[:-1]:
        target = target[part]
    del target[parts[-1]]
    return entry


# ==== INPUT ====

def test_fixtures_valid_league_and_season_accepted():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    assert result.fixtures[0].provider_fixture_id == 555


@pytest.mark.parametrize("league_id", [True, 0, -135, "135"])
def test_fixtures_invalid_league_id_rejected_before_http(league_id):
    client = _client(_handler_that_must_not_be_called)
    with pytest.raises(ApiFootballError):
        client.get_fixtures(league_id, 2023, job_run_id="job-1")


@pytest.mark.parametrize("season", [True, 999, 10000, "2023"])
def test_fixtures_invalid_season_rejected_before_http(season):
    client = _client(_handler_that_must_not_be_called)
    with pytest.raises(ApiFootballError):
        client.get_fixtures(135, season, job_run_id="job-1")


@pytest.mark.parametrize("job_run_id", ["", "   ", 123])
def test_fixtures_invalid_job_run_id_rejected_before_http(job_run_id):
    client = _client(_handler_that_must_not_be_called)
    with pytest.raises(ApiFootballError):
        client.get_fixtures(135, 2023, job_run_id=job_run_id)


# ==== REQUEST / REQUEST IDENTITY ====

def test_fixtures_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["league"] = request.url.params.get("league")
        seen["season"] = request.url.params.get("season")
        seen["auth"] = request.headers.get("x-apisports-key")
        return httpx.Response(200, content=_valid_fixtures_envelope([VALID_FIXTURE_ENTRY]))

    client = _client(handler, api_key=API_KEY)
    client.get_fixtures(135, 2023, job_run_id="job-1")
    assert seen["host"] == "v3.football.api-sports.io"
    assert seen["path"] == "/fixtures"
    assert seen["league"] == "135"
    assert seen["season"] == "2023"
    assert seen["auth"] == API_KEY


def test_fixtures_logical_identity_contains_league_and_season_but_not_credentials_or_job_run_id():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])), api_key="key-one")
    first = client.get_fixtures(135, 2023, job_run_id="job-1")

    client2 = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])), api_key="key-two")
    second = client2.get_fixtures(135, 2023, job_run_id="job-2")

    assert dict(first.observation.logical_request.parameters) == {"league": "135", "season": "2023"}
    assert first.observation.logical_request == second.observation.logical_request
    assert "key-one" not in repr(first.observation.logical_request)
    assert "job-1" not in repr(first.observation.logical_request)


# ==== RAW PROVENANCE ====

def test_fixtures_exact_bytes_and_fingerprint_retained():
    envelope = {
        "get": "fixtures",
        "parameters": {"league": "135", "season": "2023"},
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": [VALID_FIXTURE_ENTRY],
    }
    # Deliberately non-canonical formatting (indented, spaced separators)
    # so this proves exact raw bytes are retained rather than merely
    # equivalent JSON being reconstructed.
    exact_bytes = json.dumps(envelope, indent=2, separators=(",", ": ")).encode("utf-8")
    client = _client(_handler_returning(200, exact_bytes))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")

    assert result.observation.raw_content.body == exact_bytes
    assert result.observation.raw_content.content_fingerprint == hashlib.sha256(exact_bytes).hexdigest()

    reserialized = json.dumps(json.loads(exact_bytes)).encode("utf-8")
    assert reserialized != exact_bytes
    assert hashlib.sha256(reserialized).hexdigest() != result.observation.raw_content.content_fingerprint


def test_fixtures_raw_observation_request_parameters_match_league_and_season():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    assert dict(result.observation.request_parameters) == {"league": "135", "season": "2023"}
    assert API_KEY not in result.observation.request_parameters.values()


def test_fixtures_timestamps_are_utc():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    assert result.observation.requested_at.tzinfo is not None
    assert result.observation.received_at.tzinfo is not None
    assert result.observation.received_at >= result.observation.requested_at


def test_observation_retained_on_malformed_fixture_response():
    bad_entry = _delete_path(_fixture_entry(), "fixture.status.long")
    client = _client(_handler_returning(200, _valid_fixtures_envelope([bad_entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.http_status == 200


# ==== UNICODE / JSON ====

def test_fixtures_malformed_json_rejected():
    client = _client(_handler_returning(200, b"not json at all {"))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_fixtures_invalidly_encoded_bytes_rejected_with_observation_retained():
    client = _client(_handler_returning(200, INVALID_UTF16_BYTES))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == INVALID_UTF16_BYTES


# ==== ENVELOPE / PAGINATION ====

def test_fixtures_malformed_envelope_rejected():
    body = json.dumps({"get": "fixtures"}).encode("utf-8")
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_fixtures_provider_errors_rejected():
    body = json.dumps(
        {
            "get": "fixtures",
            "parameters": {"league": "135", "season": "2023"},
            "errors": {"season": "Invalid season"},
            "results": 0,
            "paging": {"current": 1, "total": 1},
            "response": [],
        }
    ).encode("utf-8")
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballProviderError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.provider_errors == {"season": "Invalid season"}


def test_fixtures_http_non_success_rejected():
    client = _client(_handler_returning(500, b"internal error"))
    with pytest.raises(ApiFootballHttpError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.status_code == 500
    assert excinfo.value.observation is not None


def test_fixtures_single_complete_page_accepted():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    assert result.fixtures[0].provider_fixture_id == 555


@pytest.mark.parametrize(
    "paging",
    [
        {"total": 1},
        {"current": True, "total": 1},
        {"current": "1", "total": 1},
        {"current": 0, "total": 1},
        {"current": -1, "total": 1},
        {"current": 2, "total": 1},
        {"current": 1},
        {"current": 1, "total": True},
        {"current": 1, "total": "1"},
        {"current": 1, "total": 0},
        {"current": 1, "total": -1},
        {"current": 1, "total": 2},
    ],
)
def test_fixtures_invalid_paging_state_rejected(paging):
    body = json.dumps(
        {
            "get": "fixtures",
            "parameters": {"league": "135", "season": "2023"},
            "errors": [],
            "results": 1,
            "paging": paging,
            "response": [VALID_FIXTURE_ENTRY],
        }
    ).encode("utf-8")
    client = _client(_handler_returning(200, body))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


# ==== FIXTURE DTO / TIME ====

def test_fixtures_dto_full_fields_retained():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    fixture = client.get_fixtures(135, 2023, job_run_id="job-1").fixtures[0]
    assert fixture.provider_fixture_id == 555
    assert fixture.provider_league_id == 135
    assert fixture.season == 2023
    assert fixture.round == "Regular Season - 1"
    assert fixture.kickoff_at == KICKOFF_UTC
    assert fixture.kickoff_at.tzinfo == timezone.utc
    assert fixture.provider_timezone == "UTC"
    assert fixture.provider_status_short == "NS"
    assert fixture.provider_status_long == "Not Started"
    assert fixture.provider_status_elapsed is None
    assert fixture.home_provider_team_id == 505
    assert fixture.away_provider_team_id == 506
    assert fixture.home_goals is None
    assert fixture.away_goals is None


def test_fixtures_kickoff_date_with_different_offset_same_instant_accepted():
    entry = _fixture_entry(timestamp=KICKOFF_TIMESTAMP, date="2026-08-13T13:00:00-05:00")
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    fixture = client.get_fixtures(135, 2023, job_run_id="job-1").fixtures[0]
    assert fixture.kickoff_at == KICKOFF_UTC


def test_fixtures_kickoff_timestamp_date_disagreement_rejected():
    entry = _fixture_entry(date="2026-08-13T19:00:00+00:00")  # one hour off from KICKOFF_TIMESTAMP
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


@pytest.mark.parametrize("timestamp", [True, "1786644000"])
def test_fixtures_kickoff_timestamp_invalid_type_rejected(timestamp):
    entry = _fixture_entry(timestamp=timestamp)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


# 0.5.4D: a structurally valid int can still be outside the
# platform/Python datetime representable range. Empirically verified in
# this environment: 10**18 raises OSError via datetime.fromtimestamp();
# the fix must convert this (and OverflowError/ValueError) into
# ApiFootballMalformedResponseError rather than letting it escape.
EXTREME_POSITIVE_TIMESTAMP = 10**18
EXTREME_NEGATIVE_TIMESTAMP = -(10**18)


def test_fixtures_extreme_positive_timestamp_rejected():
    entry = _fixture_entry(timestamp=EXTREME_POSITIVE_TIMESTAMP)
    exact_bytes = _valid_fixtures_envelope([entry])
    client = _client(_handler_returning(200, exact_bytes))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == exact_bytes


def test_fixtures_extreme_negative_timestamp_rejected():
    entry = _fixture_entry(timestamp=EXTREME_NEGATIVE_TIMESTAMP)
    exact_bytes = _valid_fixtures_envelope([entry])
    client = _client(_handler_returning(200, exact_bytes))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == exact_bytes


def test_fixtures_iso_date_utc_normalization_overflow_rejected():
    # Syntactically valid ISO 8601, timezone-aware, parses fine via
    # fromisoformat -- but normalizing to UTC shifts it past year 9999,
    # overflowing datetime's representable range. Paired with an
    # ordinary, valid timestamp so this exercises the date-normalization
    # overflow specifically, not the timestamp-range fix.
    entry = _fixture_entry(timestamp=KICKOFF_TIMESTAMP, date="9999-12-31T23:59:59-14:00")
    exact_bytes = _valid_fixtures_envelope([entry])
    client = _client(_handler_returning(200, exact_bytes))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None
    assert excinfo.value.observation.raw_content.body == exact_bytes


def test_fixtures_kickoff_date_missing_offset_rejected():
    entry = _fixture_entry(date="2026-08-13T20:00:00")  # naive, no offset
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


def test_fixtures_kickoff_date_malformed_rejected():
    entry = _fixture_entry(date="not-a-date")
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


def test_fixtures_kickoff_date_blank_rejected():
    entry = _fixture_entry(date="   ")
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


def test_fixtures_timezone_blank_rejected():
    entry = _fixture_entry(tz="   ")
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


# ==== LEAGUE / SEASON CONSISTENCY ====

def test_fixtures_league_id_mismatch_rejected():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(999, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_fixtures_season_mismatch_rejected():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2099, job_run_id="job-1")
    assert excinfo.value.observation is not None


def test_fixtures_response_league_id_wrong_type_rejected():
    entry = _fixture_entry(league_id="135")
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


def test_fixtures_response_season_out_of_range_rejected():
    entry = _fixture_entry(season=42)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


# ==== ROUND ====

@pytest.mark.parametrize("round_value", ["Regular Season - 1", None])
def test_fixtures_round_valid_values_accepted(round_value):
    entry = _fixture_entry(round_=round_value)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    fixture = client.get_fixtures(135, 2023, job_run_id="job-1").fixtures[0]
    assert fixture.round == round_value


@pytest.mark.parametrize("round_value", ["", "   ", 123])
def test_fixtures_round_invalid_values_rejected(round_value):
    entry = _fixture_entry(round_=round_value)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


# ==== TEAMS ====

@pytest.mark.parametrize("team_id", [True, 0, -505, "505"])
def test_fixtures_home_team_id_invalid_rejected(team_id):
    entry = _fixture_entry(home_id=team_id)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


def test_fixtures_equal_home_away_ids_rejected():
    entry = _fixture_entry(home_id=505, away_id=505)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


# ==== STATUS ====

@pytest.mark.parametrize("field,value", [("status_short", ""), ("status_short", 123), ("status_long", ""), ("status_long", 123)])
def test_fixtures_status_short_or_long_invalid_rejected(field, value):
    entry = _fixture_entry(**{field: value})
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


@pytest.mark.parametrize("elapsed", [None, 0, 45])
def test_fixtures_status_elapsed_valid_values_accepted(elapsed):
    entry = _fixture_entry(elapsed=elapsed)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    fixture = client.get_fixtures(135, 2023, job_run_id="job-1").fixtures[0]
    assert fixture.provider_status_elapsed == elapsed


@pytest.mark.parametrize("elapsed", [True, -1, "45"])
def test_fixtures_status_elapsed_invalid_values_rejected(elapsed):
    entry = _fixture_entry(elapsed=elapsed)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


# ==== GOALS ====

@pytest.mark.parametrize("home_goals,away_goals", [(None, None), (2, 1), (None, 3), (4, None)])
def test_fixtures_goals_valid_combinations_accepted(home_goals, away_goals):
    entry = _fixture_entry(home_goals=home_goals, away_goals=away_goals)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    fixture = client.get_fixtures(135, 2023, job_run_id="job-1").fixtures[0]
    assert fixture.home_goals == home_goals
    assert fixture.away_goals == away_goals


@pytest.mark.parametrize(
    "field,value",
    [
        ("home_goals", True),
        ("home_goals", -1),
        ("home_goals", "2"),
        ("away_goals", True),
        ("away_goals", -1),
        ("away_goals", "2"),
    ],
)
def test_fixtures_goals_invalid_values_rejected(field, value):
    entry = _fixture_entry(**{field: value})
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError):
        client.get_fixtures(135, 2023, job_run_id="job-1")


# ==== NULLABILITY / STRUCTURE (all required keys) ====

_FIXTURE_REQUIRED_PATHS = (
    "fixture", "fixture.id", "fixture.timestamp", "fixture.date", "fixture.timezone",
    "fixture.status", "fixture.status.short", "fixture.status.long", "fixture.status.elapsed",
    "league", "league.id", "league.season", "league.round",
    "teams", "teams.home", "teams.home.id", "teams.away", "teams.away.id",
    "goals", "goals.home", "goals.away",
)


@pytest.mark.parametrize("path", _FIXTURE_REQUIRED_PATHS)
def test_fixtures_missing_required_key_rejected(path):
    entry = _delete_path(_fixture_entry(), path)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


# ==== DUPLICATES / ORDER / EMPTY / MALFORMED ITEM ====

def test_fixtures_duplicate_provider_fixture_ids_rejected():
    duplicate = _fixture_entry(fixture_id=555, home_id=507, away_id=508)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY, duplicate])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert "555" in str(excinfo.value)
    assert excinfo.value.observation is not None


def test_fixtures_provider_order_preserved():
    # Deliberately non-sorted provider sequence (557, 555, 556): if
    # production code ever accidentally sorted ascending by ID, this
    # would fail where an ascending input sequence would not catch it.
    non_sorted = [THIRD_VALID_FIXTURE_ENTRY, VALID_FIXTURE_ENTRY, SECOND_VALID_FIXTURE_ENTRY]
    client = _client(_handler_returning(200, _valid_fixtures_envelope(non_sorted)))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    assert [fixture.provider_fixture_id for fixture in result.fixtures] == [557, 555, 556]


def test_fixtures_valid_empty_response_returns_empty_tuple():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([])))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    assert result.fixtures == ()
    assert result.observation is not None


def test_fixtures_malformed_second_entry_fails_whole_result_no_partial_return():
    bad_entry = _delete_path(_fixture_entry(fixture_id=556, home_id=507, away_id=508), "goals.home")
    third_entry = _fixture_entry(fixture_id=557, home_id=509, away_id=510)
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY, bad_entry, third_entry])))
    with pytest.raises(ApiFootballMalformedResponseError) as excinfo:
        client.get_fixtures(135, 2023, job_run_id="job-1")
    assert excinfo.value.observation is not None


# ==== PUBLIC API (via api_football module) ====

def test_fixtures_dto_never_carries_footcap_identity():
    client = _client(_handler_returning(200, _valid_fixtures_envelope([VALID_FIXTURE_ENTRY])))
    result = client.get_fixtures(135, 2023, job_run_id="job-1")
    fixture_fields = {f.name for f in dataclasses.fields(result.fixtures[0])}
    assert not any(name in ("match_id", "competition_id", "season_id") or "footcap" in name.lower() for name in fixture_fields)
