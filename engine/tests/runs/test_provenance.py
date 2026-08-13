"""
Executable invariant test matrix for the Run / Provenance Engine (Task
0.4.4H section 23), plus the minimal schema-structural proof for
job_run_id (section 22). RunStatus/JobType contract-drift tests live in
test_contract_drift.py, not here.

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath -- it only adds "tests" (for the existing
support.schema_loader import pattern used by engine/tests/contracts/).
Without it, footcap_engine would not be importable from this file.
"""
import copy
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from footcap_engine.runs import (
    ExecutionContext,
    RunInputError,
    RunProvenance,
    validate_run_provenance,
)
from support.schema_loader import validator_for

STARTED = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
FINISHED = STARTED + timedelta(minutes=5)


def _provenance(**overrides):
    fields = dict(
        job_run_id="job-run-0001",
        job_type="training",
        status="PENDING",
        started_at=STARTED,
        trigger="manual",
        environment="local",
    )
    fields.update(overrides)
    return RunProvenance(**fields)


# ==== EXECUTION CONTEXT (matrix items 1-10) ====

def test_local_clean_valid():
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="CLEAN")
    assert ctx.origin == "LOCAL"
    assert ctx.working_tree_state == "CLEAN"


def test_local_dirty_valid():
    ExecutionContext(origin="LOCAL", working_tree_state="DIRTY")


def test_local_unknown_valid():
    ExecutionContext(origin="LOCAL", working_tree_state="UNKNOWN")


def test_local_not_applicable_invalid():
    with pytest.raises(RunInputError):
        ExecutionContext(origin="LOCAL", working_tree_state="NOT_APPLICABLE")


def test_ci_not_applicable_valid():
    ExecutionContext(origin="CI", working_tree_state="NOT_APPLICABLE")


def test_ci_clean_invalid():
    with pytest.raises(RunInputError):
        ExecutionContext(origin="CI", working_tree_state="CLEAN")


def test_github_actions_not_applicable_valid():
    ExecutionContext(origin="GITHUB_ACTIONS", working_tree_state="NOT_APPLICABLE")


def test_github_actions_dirty_invalid():
    with pytest.raises(RunInputError):
        ExecutionContext(origin="GITHUB_ACTIONS", working_tree_state="DIRTY")


def test_invalid_origin_rejected():
    with pytest.raises(RunInputError):
        ExecutionContext(origin="REMOTE", working_tree_state="NOT_APPLICABLE")


def test_invalid_working_tree_state_rejected():
    with pytest.raises(RunInputError):
        ExecutionContext(origin="LOCAL", working_tree_state="MAYBE")


# ==== RUN IDENTIFIERS / STRINGS (matrix items 11-17) ====

def test_valid_job_run_id():
    prov = _provenance(job_run_id="abc-123")
    assert prov.job_run_id == "abc-123"


def test_empty_job_run_id_rejected():
    with pytest.raises(RunInputError):
        _provenance(job_run_id="")


def test_whitespace_job_run_id_rejected():
    with pytest.raises(RunInputError):
        _provenance(job_run_id="   ")


def test_invalid_job_type_rejected():
    with pytest.raises(RunInputError):
        _provenance(job_type="not-a-job-type")


def test_invalid_run_status_rejected():
    with pytest.raises(RunInputError):
        _provenance(status="NOT_A_STATUS")


def test_blank_trigger_rejected():
    with pytest.raises(RunInputError):
        _provenance(trigger="   ")


def test_blank_environment_rejected():
    with pytest.raises(RunInputError):
        _provenance(environment="")


# ==== DATETIME (matrix items 18-25) ====

def test_utc_started_at_accepted():
    prov = _provenance(started_at=STARTED)
    assert prov.started_at == STARTED
    assert prov.started_at.tzinfo == timezone.utc


def test_aware_non_utc_started_at_normalized():
    non_utc = STARTED.astimezone(timezone(timedelta(hours=3)))
    prov = _provenance(started_at=non_utc)
    assert prov.started_at == STARTED
    assert prov.started_at.tzinfo == timezone.utc


def test_naive_started_at_rejected():
    with pytest.raises(RunInputError):
        _provenance(started_at=datetime(2026, 8, 10, 12, 0, 0))


class _PseudoAwareTzinfo(tzinfo):
    """A tzinfo whose utcoffset() returns None -- proves rejection of
    pseudo-aware datetimes, not merely naive ones."""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "PSEUDO"


def test_pseudo_aware_started_at_rejected():
    pseudo_aware = datetime(2026, 8, 10, 12, 0, 0, tzinfo=_PseudoAwareTzinfo())
    with pytest.raises(RunInputError):
        _provenance(started_at=pseudo_aware)


def test_wrong_started_at_type_rejected():
    with pytest.raises(RunInputError):
        _provenance(started_at="2026-08-10T12:00:00Z")


def test_terminal_finished_at_normalized():
    non_utc_finished = FINISHED.astimezone(timezone(timedelta(hours=3)))
    prov = _provenance(status="COMPLETED", finished_at=non_utc_finished)
    assert prov.finished_at == FINISHED
    assert prov.finished_at.tzinfo == timezone.utc


def test_finished_at_before_started_at_rejected():
    with pytest.raises(RunInputError, match="finished_at"):
        _provenance(status="COMPLETED", finished_at=STARTED - timedelta(seconds=1))


def test_finished_at_equal_started_at_accepted():
    prov = _provenance(status="COMPLETED", finished_at=STARTED)
    assert prov.finished_at == STARTED


# ==== STATUS / FINISHED_AT (matrix items 26-30) ====

def test_pending_without_finished_at_valid():
    prov = _provenance(status="PENDING")
    assert prov.finished_at is None


def test_running_without_finished_at_valid():
    prov = _provenance(status="RUNNING")
    assert prov.finished_at is None


def test_pending_with_finished_at_rejected():
    with pytest.raises(RunInputError):
        _provenance(status="PENDING", finished_at=FINISHED)


def test_running_with_finished_at_rejected():
    with pytest.raises(RunInputError):
        _provenance(status="RUNNING", finished_at=FINISHED)


@pytest.mark.parametrize("status", ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"])
def test_terminal_status_requires_finished_at(status):
    error_summary = "boom" if status in ("PARTIAL", "FAILED", "CANCELLED") else None
    with pytest.raises(RunInputError, match="finished_at"):
        _provenance(status=status, error_summary=error_summary)


# ==== ERROR SUMMARY (matrix items 31-37) ====

def test_failed_requires_error_summary():
    with pytest.raises(RunInputError, match="error_summary"):
        _provenance(status="FAILED", finished_at=FINISHED, error_summary=None)


def test_partial_requires_error_summary():
    with pytest.raises(RunInputError, match="error_summary"):
        _provenance(status="PARTIAL", finished_at=FINISHED, error_summary=None)


def test_cancelled_requires_error_summary():
    with pytest.raises(RunInputError, match="error_summary"):
        _provenance(status="CANCELLED", finished_at=FINISHED, error_summary=None)


def test_completed_forbids_error_summary():
    with pytest.raises(RunInputError, match="error_summary"):
        _provenance(status="COMPLETED", finished_at=FINISHED, error_summary="boom")


def test_running_forbids_error_summary():
    with pytest.raises(RunInputError, match="error_summary"):
        _provenance(status="RUNNING", error_summary="boom")


def test_pending_forbids_error_summary():
    with pytest.raises(RunInputError, match="error_summary"):
        _provenance(status="PENDING", error_summary="boom")


def test_blank_required_error_summary_rejected():
    with pytest.raises(RunInputError):
        _provenance(status="FAILED", finished_at=FINISHED, error_summary="   ")


# ==== GIT PAIR (matrix items 38-41) ====

def test_both_git_fields_present_valid_intrinsically():
    prov = _provenance(git_commit="abc123", git_ref="main")
    assert prov.git_commit == "abc123"
    assert prov.git_ref == "main"


def test_both_git_fields_absent_valid_intrinsically():
    prov = _provenance()
    assert prov.git_commit is None
    assert prov.git_ref is None


def test_git_commit_only_rejected():
    with pytest.raises(RunInputError):
        _provenance(git_commit="abc123")


def test_git_ref_only_rejected():
    with pytest.raises(RunInputError):
        _provenance(git_ref="main")


# ==== LOCAL CONTEXTUAL (matrix items 42-48) ====

def test_local_clean_git_pair_present_valid():
    prov = _provenance(git_commit="abc123", git_ref="main")
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="CLEAN")
    assert validate_run_provenance(prov, ctx) is prov


def test_local_clean_git_pair_absent_valid():
    prov = _provenance()
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="CLEAN")
    assert validate_run_provenance(prov, ctx) is prov


def test_local_dirty_git_absent_valid():
    prov = _provenance()
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="DIRTY")
    assert validate_run_provenance(prov, ctx) is prov


def test_local_dirty_git_present_rejected():
    prov = _provenance(git_commit="abc123", git_ref="main")
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="DIRTY")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


def test_local_unknown_git_absent_valid():
    prov = _provenance()
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="UNKNOWN")
    assert validate_run_provenance(prov, ctx) is prov


def test_local_unknown_git_present_rejected():
    prov = _provenance(git_commit="abc123", git_ref="main")
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="UNKNOWN")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


def test_local_workflow_run_id_rejected():
    prov = _provenance(workflow_run_id="12345")
    ctx = ExecutionContext(origin="LOCAL", working_tree_state="CLEAN")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


# ==== GENERIC CI CONTEXTUAL (matrix items 49-51) ====

def test_ci_git_pair_present_no_workflow_valid():
    prov = _provenance(git_commit="abc123", git_ref="main")
    ctx = ExecutionContext(origin="CI", working_tree_state="NOT_APPLICABLE")
    assert validate_run_provenance(prov, ctx) is prov


def test_ci_without_git_rejected():
    prov = _provenance()
    ctx = ExecutionContext(origin="CI", working_tree_state="NOT_APPLICABLE")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


def test_ci_with_workflow_run_id_rejected():
    prov = _provenance(git_commit="abc123", git_ref="main", workflow_run_id="12345")
    ctx = ExecutionContext(origin="CI", working_tree_state="NOT_APPLICABLE")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


# ==== GITHUB ACTIONS CONTEXTUAL (matrix items 52-54) ====

def test_github_actions_git_and_workflow_id_valid():
    prov = _provenance(git_commit="abc123", git_ref="main", workflow_run_id="12345")
    ctx = ExecutionContext(origin="GITHUB_ACTIONS", working_tree_state="NOT_APPLICABLE")
    assert validate_run_provenance(prov, ctx) is prov


def test_github_actions_missing_git_rejected():
    prov = _provenance(workflow_run_id="12345")
    ctx = ExecutionContext(origin="GITHUB_ACTIONS", working_tree_state="NOT_APPLICABLE")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


def test_github_actions_missing_workflow_id_rejected():
    prov = _provenance(git_commit="abc123", git_ref="main")
    ctx = ExecutionContext(origin="GITHUB_ACTIONS", working_tree_state="NOT_APPLICABLE")
    with pytest.raises(RunInputError):
        validate_run_provenance(prov, ctx)


# ==== METADATA (matrix items 55-63) ====

def test_empty_metadata_valid():
    prov = _provenance(metadata={})
    assert dict(prov.metadata) == {}


def test_nested_json_compatible_metadata_valid():
    metadata = {
        "a": 1,
        "b": 2.5,
        "c": "text",
        "d": True,
        "e": None,
        "f": [1, "two", {"nested": True}],
        "g": {"deep": {"deeper": [1, 2, 3]}},
    }
    prov = _provenance(metadata=metadata)
    assert prov.metadata["a"] == 1
    assert prov.metadata["f"][1] == "two"
    assert prov.metadata["f"][2]["nested"] is True
    assert prov.metadata["g"]["deep"]["deeper"] == (1, 2, 3)


def test_non_string_metadata_key_rejected():
    with pytest.raises(RunInputError):
        _provenance(metadata={1: "value"})


def test_arbitrary_object_metadata_rejected():
    class _Unsupported:
        pass

    with pytest.raises(RunInputError):
        _provenance(metadata={"x": _Unsupported()})


def test_nan_metadata_rejected():
    with pytest.raises(RunInputError):
        _provenance(metadata={"x": float("nan")})


def test_positive_infinity_metadata_rejected():
    with pytest.raises(RunInputError):
        _provenance(metadata={"x": float("inf")})


def test_negative_infinity_metadata_rejected():
    with pytest.raises(RunInputError):
        _provenance(metadata={"x": float("-inf")})


def test_metadata_defensive_copy():
    original = {"a": [1, 2, 3]}
    prov = _provenance(metadata=original)
    original["a"].append(4)
    original["b"] = "new"
    assert prov.metadata["a"] == (1, 2, 3)
    assert "b" not in prov.metadata


def test_nested_metadata_is_immutable():
    prov = _provenance(metadata={"a": {"b": 1}})
    assert isinstance(prov.metadata, MappingProxyType)
    assert isinstance(prov.metadata["a"], MappingProxyType)
    with pytest.raises(TypeError):
        prov.metadata["a"]["b"] = 2
    with pytest.raises(TypeError):
        prov.metadata["a"] = {}


# ==== CONTRACT (matrix items 64-65; 66-67 live in test_contract_drift.py) ====

VALID_RUN_PROVENANCE_PAYLOAD = {
    "job_run_id": "job-run-0001",
    "job_type": "training",
    "status": "COMPLETED",
    "started_at": "2026-08-10T12:00:00Z",
    "finished_at": "2026-08-10T12:05:00Z",
    "trigger": "manual",
    "environment": "local",
}


def test_valid_run_provenance_schema_payload_passes():
    validator = validator_for("run-provenance.schema.json")
    assert validator.is_valid(VALID_RUN_PROVENANCE_PAYLOAD)


def test_missing_job_run_id_schema_payload_fails():
    payload = copy.deepcopy(VALID_RUN_PROVENANCE_PAYLOAD)
    del payload["job_run_id"]
    validator = validator_for("run-provenance.schema.json")
    assert not validator.is_valid(payload)
