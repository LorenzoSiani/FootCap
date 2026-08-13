"""
httpx.MockTransport-based integration tests for ApiFootballClient. No
unit test in this file requires internet access -- every request is
served by an in-process MockTransport handler.

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath.
"""
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
