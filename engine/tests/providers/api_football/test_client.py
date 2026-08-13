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
