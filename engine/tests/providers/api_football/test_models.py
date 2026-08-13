"""
Pure unit tests for footcap_engine.providers.api_football value types --
ApiFootballConfig, RawContent, LogicalRequestIdentity, HttpRequestIdentity,
RawObservation, ApiFootballLeague, LeagueFetchResult. No HTTP transport
involved; see test_client.py for MockTransport-based integration tests.

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath.
"""
import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

import footcap_engine.providers.api_football as api_football
from footcap_engine.providers.api_football import (
    ApiFootballConfig,
    ApiFootballError,
    ApiFootballLeague,
    ApiFootballMalformedResponseError,
    ApiFootballTeam,
    HttpRequestIdentity,
    LeagueFetchResult,
    LogicalRequestIdentity,
    RawContent,
    RawObservation,
    TeamsFetchResult,
)

REQUESTED = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
RECEIVED = REQUESTED + timedelta(milliseconds=50)


def _identity(league_id: str = "135") -> LogicalRequestIdentity:
    return LogicalRequestIdentity(provider="api-football", endpoint="/leagues", parameters=(("id", league_id),))


def _observation(**overrides) -> RawObservation:
    logical = overrides.pop("logical_request", _identity())
    fields = dict(
        provider=logical.provider,
        endpoint=logical.endpoint,
        logical_request=logical,
        http_request=HttpRequestIdentity(logical_request=logical),
        request_parameters={"id": "135"},
        requested_at=REQUESTED,
        received_at=RECEIVED,
        http_status=200,
        job_run_id="job-1",
        raw_content=RawContent(body=b'{"a": 1}'),
    )
    fields.update(overrides)
    return RawObservation(**fields)


# ==== CONFIG (matrix items 1-4) ====

def test_valid_config():
    config = ApiFootballConfig(api_key="secret-key-1")
    assert config.base_url == "https://v3.football.api-sports.io"
    assert config.connect_timeout_seconds == 5.0
    assert config.read_timeout_seconds == 30.0


def test_blank_api_key_rejected():
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="   ")


def test_config_repr_hides_api_key():
    config = ApiFootballConfig(api_key="super-secret-value")
    assert "super-secret-value" not in repr(config)
    assert "super-secret-value" not in str(config)


@pytest.mark.parametrize("timeout_kwargs", [{"connect_timeout_seconds": 0}, {"connect_timeout_seconds": -1}, {"read_timeout_seconds": 0}, {"read_timeout_seconds": -5}])
def test_non_positive_timeout_rejected(timeout_kwargs):
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="key", **timeout_kwargs)


# ==== 0.5.1F FIX 1: base_url constrained to the direct API-Sports host ====

def test_canonical_direct_base_url_accepted():
    config = ApiFootballConfig(api_key="key")
    assert config.base_url == "https://v3.football.api-sports.io"
    # explicit form (with the harmless trailing slash httpx normalization allows) also accepted
    ApiFootballConfig(api_key="key", base_url="https://v3.football.api-sports.io/")


def test_arbitrary_foreign_https_host_rejected():
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="key", base_url="https://evil.example.com")


def test_http_api_sports_url_rejected():
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="key", base_url="http://v3.football.api-sports.io")


def test_lookalike_suffix_host_rejected():
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="key", base_url="https://v3.football.api-sports.io.example.com")


def test_rapidapi_host_rejected():
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="key", base_url="https://api-football-v1.p.rapidapi.com")


def test_valid_config_repr_still_hides_api_key_after_host_fix():
    config = ApiFootballConfig(api_key="another-super-secret")
    assert "another-super-secret" not in repr(config)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:pass@v3.football.api-sports.io",  # userinfo
        "https://v3.football.api-sports.io:8443",  # arbitrary port
        "https://v3.football.api-sports.io/leagues",  # unexpected path
        "https://v3.football.api-sports.io?x=1",  # query
    ],
)
def test_base_url_rejects_userinfo_port_path_and_query(base_url):
    with pytest.raises(ApiFootballError):
        ApiFootballConfig(api_key="key", base_url=base_url)


# ==== RAW CONTENT (matrix items 13-15, 21) ====

def test_raw_content_body_preserved_exactly():
    body = b'{"z": 1, "a": 2}'
    content = RawContent(body=body)
    assert content.body == body


def test_raw_content_fingerprint_computed_from_exact_bytes():
    content = RawContent(body=b"hello world")
    assert isinstance(content.content_fingerprint, str) and content.content_fingerprint

    import hashlib
    assert content.content_fingerprint == hashlib.sha256(b"hello world").hexdigest()


def test_reserialized_json_would_differ_but_fingerprint_matches_original_bytes():
    import json

    original_bytes = b'{"b": 2,   "a": 1}'  # deliberately unusual whitespace/key order
    reserialized_bytes = json.dumps(json.loads(original_bytes), sort_keys=True).encode("utf-8")
    assert original_bytes != reserialized_bytes

    original_content = RawContent(body=original_bytes)
    reserialized_content = RawContent(body=reserialized_bytes)
    assert original_content.content_fingerprint != reserialized_content.content_fingerprint

    # constructing again from the same original bytes always reproduces the same fingerprint
    assert RawContent(body=original_bytes).content_fingerprint == original_content.content_fingerprint


def test_same_bytes_produce_same_content_fingerprint():
    assert RawContent(body=b"identical").content_fingerprint == RawContent(body=b"identical").content_fingerprint


# ==== RAW OBSERVATION (matrix items 16-20) ====

def test_requested_at_must_be_utc_aware():
    with pytest.raises(ApiFootballError):
        _observation(requested_at=datetime(2026, 8, 10, 12, 0, 0))  # naive


def test_received_at_must_be_utc_aware():
    with pytest.raises(ApiFootballError):
        _observation(received_at=datetime(2026, 8, 10, 12, 0, 0))  # naive


def test_received_at_before_requested_at_rejected():
    with pytest.raises(ApiFootballError):
        _observation(requested_at=RECEIVED, received_at=REQUESTED)


def test_received_at_equal_requested_at_accepted():
    observation = _observation(requested_at=REQUESTED, received_at=REQUESTED)
    assert observation.received_at == observation.requested_at


def test_request_parameters_contain_league_id_only():
    observation = _observation(request_parameters={"id": "135"})
    assert dict(observation.request_parameters) == {"id": "135"}


def test_two_observations_with_identical_content_are_distinct_objects():
    body = b'{"same": true}'
    first = _observation(raw_content=RawContent(body=body), job_run_id="job-1")
    second = _observation(raw_content=RawContent(body=body), job_run_id="job-2")
    assert first is not second
    assert first != second  # job_run_id differs
    assert first.raw_content.content_fingerprint == second.raw_content.content_fingerprint


# ==== 0.5.1F FIX 2: request_parameters must agree with logical_request.parameters ====

def test_matching_logical_and_request_parameters_accepted():
    observation = _observation(logical_request=_identity("135"), request_parameters={"id": "135"})
    assert dict(observation.request_parameters) == {"id": "135"}


def test_different_request_parameter_value_rejected():
    with pytest.raises(ApiFootballError):
        _observation(logical_request=_identity("135"), request_parameters={"id": "140"})


def test_missing_logical_parameter_in_request_parameters_rejected():
    two_param_logical = LogicalRequestIdentity(
        provider="api-football", endpoint="/leagues", parameters=(("id", "135"), ("foo", "bar"))
    )
    with pytest.raises(ApiFootballError):
        _observation(logical_request=two_param_logical, request_parameters={"id": "135"})


def test_extra_request_parameter_not_in_logical_identity_rejected():
    with pytest.raises(ApiFootballError):
        _observation(logical_request=_identity("135"), request_parameters={"id": "135", "extra": "unexpected"})


# ==== REQUEST IDENTITY (matrix items 22-25) ====

def test_same_league_id_gives_same_logical_identity():
    assert _identity("135") == _identity("135")


def test_different_league_id_gives_different_logical_identity():
    assert _identity("135") != _identity("140")


def test_logical_identity_excludes_api_key_and_job_run_id_by_construction():
    # LogicalRequestIdentity has no field for either -- constructing it
    # for the same league id is identical regardless of what API key or
    # job_run_id the caller happens to be using for this execution.
    identity_fields = {f for f in vars(_identity("135"))}
    assert "api_key" not in identity_fields
    assert "job_run_id" not in identity_fields


def test_http_request_identity_wraps_logical_identity():
    logical = _identity("135")
    http_request = HttpRequestIdentity(logical_request=logical)
    assert http_request.logical_request == logical


# ==== LEAGUE DTO (matrix items 32-34) ====

def test_league_provider_id_retained():
    league = ApiFootballLeague(provider_league_id=135, name="Serie A", type="League", logo=None, country_name=None)
    assert league.provider_league_id == 135


def test_league_name_retained():
    league = ApiFootballLeague(provider_league_id=135, name="Serie A", type="League", logo=None, country_name=None)
    assert league.name == "Serie A"


def test_malformed_required_league_field_rejected():
    with pytest.raises(ApiFootballMalformedResponseError):
        ApiFootballLeague(provider_league_id=135, name="", type="League", logo=None, country_name=None)


def test_malformed_league_id_type_rejected():
    with pytest.raises(ApiFootballMalformedResponseError):
        ApiFootballLeague(provider_league_id="135", name="Serie A", type="League", logo=None, country_name=None)


# ==== LeagueFetchResult ====

def test_league_fetch_result_accepts_none_league():
    result = LeagueFetchResult(observation=_observation(), league=None)
    assert result.league is None


def test_league_fetch_result_rejects_wrong_league_type():
    with pytest.raises(ApiFootballError):
        LeagueFetchResult(observation=_observation(), league="not a league")


# ==== TEAM DTO (matrix items 28-38, 46-54) ====

def _team(**overrides) -> ApiFootballTeam:
    fields = dict(
        provider_team_id=505,
        name="Inter",
        code="INT",
        country="Italy",
        founded=1908,
        national=False,
        logo="https://example.test/teams/505.png",
    )
    fields.update(overrides)
    return ApiFootballTeam(**fields)


def test_team_provider_id_and_name_retained():
    team = _team()
    assert team.provider_team_id == 505
    assert team.name == "Inter"


def test_team_nullable_fields_accept_none():
    team = _team(code=None, country=None, founded=None, logo=None)
    assert team.code is None
    assert team.country is None
    assert team.founded is None
    assert team.logo is None


def test_team_national_bool_retained():
    assert _team(national=True).national is True
    assert _team(national=False).national is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_team_id": True},  # bool rejected
        {"provider_team_id": 0},  # non-positive rejected
        {"provider_team_id": -505},  # negative rejected
        {"name": ""},  # blank rejected
        {"name": "   "},  # whitespace-only rejected
        {"code": ""},  # blank (not None) rejected
        {"country": "   "},  # whitespace-only (not None) rejected
        {"founded": True},  # bool rejected
        {"founded": 0},  # non-positive rejected
        {"founded": -1908},  # negative rejected
        {"national": 1},  # int truthy, not accepted as bool
        {"national": None},  # null rejected -- national is required
        {"logo": ""},  # blank (not None) rejected
    ],
)
def test_team_invalid_values_rejected(overrides):
    with pytest.raises(ApiFootballMalformedResponseError):
        _team(**overrides)


# ==== TeamsFetchResult (matrix items 55, 16-17 collection immutability) ====

def test_teams_fetch_result_accepts_empty_tuple():
    result = TeamsFetchResult(observation=_observation(), teams=())
    assert result.teams == ()


def test_teams_fetch_result_accepts_tuple_of_teams():
    result = TeamsFetchResult(observation=_observation(), teams=(_team(), _team(provider_team_id=506)))
    assert isinstance(result.teams, tuple)
    assert len(result.teams) == 2


def test_teams_fetch_result_rejects_non_tuple_collection():
    with pytest.raises(ApiFootballError):
        TeamsFetchResult(observation=_observation(), teams=[_team()])  # list, not tuple


def test_teams_fetch_result_rejects_non_team_item():
    with pytest.raises(ApiFootballError):
        TeamsFetchResult(observation=_observation(), teams=("not a team",))


# ==== 0.5.3D FIX 3: TeamsFetchResult itself rejects duplicate provider_team_id,
# not only the _parse_teams() parser -- defense at both boundaries. ====

def test_teams_fetch_result_accepts_unique_provider_team_ids():
    result = TeamsFetchResult(observation=_observation(), teams=(_team(provider_team_id=505), _team(provider_team_id=506)))
    assert [team.provider_team_id for team in result.teams] == [505, 506]


def test_teams_fetch_result_rejects_duplicate_provider_team_ids():
    with pytest.raises(ApiFootballError):
        TeamsFetchResult(observation=_observation(), teams=(_team(provider_team_id=505), _team(provider_team_id=505)))


def test_teams_fetch_result_preserves_original_tuple_order():
    ordered = (_team(provider_team_id=507), _team(provider_team_id=505), _team(provider_team_id=506))
    result = TeamsFetchResult(observation=_observation(), teams=ordered)
    assert [team.provider_team_id for team in result.teams] == [507, 505, 506]


def test_team_dataclass_is_frozen_like_existing_provider_models():
    team = _team()
    with pytest.raises(dataclasses.FrozenInstanceError):
        team.name = "Milan"


# ==== PUBLIC API (matrix item 37) ====

def test_public_api_exports_only_intended_names():
    expected = {
        "ApiFootballClient",
        "ApiFootballConfig",
        "ApiFootballError",
        "ApiFootballHttpError",
        "ApiFootballLeague",
        "ApiFootballMalformedResponseError",
        "ApiFootballProviderError",
        "ApiFootballTeam",
        "HttpRequestIdentity",
        "LeagueFetchResult",
        "LogicalRequestIdentity",
        "RawContent",
        "TeamsFetchResult",
        "RawObservation",
    }
    assert set(api_football.__all__) == expected
    for name in expected:
        assert not name.startswith("_")
