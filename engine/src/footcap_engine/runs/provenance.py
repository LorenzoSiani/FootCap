"""
Run / Provenance Engine implementation (Architecture Baseline section 13;
ADR-010).

RunProvenance is the Phase 0 immutable domain value for the common Job Run
provenance record described by
packages/contracts/schemas/run-provenance.schema.json. Phase 0 scope is
construction and validation only -- no persistence, no lifecycle
transitions, no Git inspection, no environment inspection, no
serialization, no CLI, no orchestration (ADR-010 decision 9).

ExecutionOrigin and WorkingTreeState are internal Phase 0 domain-validation
concepts only (ADR-010 decisions 3-4). They are never serialized, never a
field on RunProvenance, and never inferred from trigger/environment/
workflow_run_id -- the caller supplies them authoritatively.

No database, network, or filesystem access. No global mutable state. Every
function here is pure with respect to its arguments.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Literal, get_args

# The cross-language source of truth for these two values remains
# packages/contracts/schemas/run-provenance.schema.json#/$defs/JobType and
# packages/contracts/schemas/definitions.schema.json#/$defs/RunStatus. These
# are plain typing.Literal, not hand-authored Enums, so they introduce no
# second, competing definition -- see engine/tests/runs/test_contract_drift.py.
JobType = Literal["ingestion", "features", "training", "prediction", "backtest"]
RunStatus = Literal["PENDING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED"]

# Internal Phase 0 domain-validation concepts only (ADR-010 decisions 3-4).
# Never serialized, never a shared contract, never a field on RunProvenance.
ExecutionOrigin = Literal["LOCAL", "CI", "GITHUB_ACTIONS"]
WorkingTreeState = Literal["CLEAN", "DIRTY", "UNKNOWN", "NOT_APPLICABLE"]

# JSON-compatible value used only for metadata's type hint and by
# _freeze_json_value; never a shared contract type.
type JsonValue = None | bool | int | float | str | Sequence[JsonValue] | Mapping[str, JsonValue]

_JOB_TYPES = frozenset(get_args(JobType))
_RUN_STATUSES = frozenset(get_args(RunStatus))
_EXECUTION_ORIGINS = frozenset(get_args(ExecutionOrigin))
_WORKING_TREE_STATES = frozenset(get_args(WorkingTreeState))

# Static record-validity invariants (ADR-010; run-provenance.schema.json
# field descriptions). Deliberately not a transition matrix -- ADR-010
# decision 9 scopes Phase 0 to construction/validation only.
_NO_FINISHED_AT_STATUSES = frozenset({"PENDING", "RUNNING"})
_REQUIRES_FINISHED_AT_STATUSES = _RUN_STATUSES - _NO_FINISHED_AT_STATUSES

_REQUIRES_ERROR_SUMMARY_STATUSES = frozenset({"FAILED", "PARTIAL", "CANCELLED"})
_FORBIDS_ERROR_SUMMARY_STATUSES = _RUN_STATUSES - _REQUIRES_ERROR_SUMMARY_STATUSES


class RunInputError(ValueError):
    """Malformed or internally inconsistent RunProvenance/ExecutionContext
    input. Never raised merely because of a normal execution status such as
    FAILED, PARTIAL, or CANCELLED."""


def _ensure_utc(value: datetime, field_name: str) -> datetime:
    """Reject non-datetime input and naive/pseudo-aware datetimes; normalize
    any genuinely timezone-aware datetime to UTC. Mirrors
    footcap_engine.temporal.evaluation._ensure_utc."""
    if not isinstance(value, datetime):
        raise RunInputError(f"{field_name} must be a datetime.datetime, got {type(value)!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise RunInputError(
            f"{field_name} must be a timezone-aware datetime; naive or pseudo-aware "
            "datetimes are rejected"
        )
    return value.astimezone(timezone.utc)


def _validate_non_blank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RunInputError(f"{field_name} must be a string, got {type(value)!r}")
    if value.strip() == "":
        raise RunInputError(f"{field_name} must not be blank or whitespace-only")
    return value


def _validate_optional_non_blank_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_non_blank_string(value, field_name)


def _freeze_json_value(value: object, path: str) -> JsonValue:
    """Recursively validate that value is JSON-compatible and return an
    immutable representation: mappings become MappingProxyType, lists/tuples
    become tuples, scalars are returned unchanged. Rejects non-string
    mapping keys, non-finite floats, and any value that is not
    JSON-compatible (e.g. an arbitrary object)."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise RunInputError(f"{path}: NaN and infinite float values are not JSON-compatible")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RunInputError(f"{path}: mapping keys must be strings, got {key!r}")
            frozen[key] = _freeze_json_value(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item, f"{path}[{index}]") for index, item in enumerate(value))
    raise RunInputError(f"{path}: value of type {type(value)!r} is not JSON-compatible")


@dataclass(frozen=True)
class ExecutionContext:
    """Internal, immutable Phase 0 execution context (ADR-010 decision 5).
    Never serialized, never a field on RunProvenance. Supplied
    authoritatively by the caller -- never inferred from
    trigger/environment/workflow_run_id, and never by inspecting Git or the
    environment."""

    origin: ExecutionOrigin
    working_tree_state: WorkingTreeState

    def __post_init__(self) -> None:
        if self.origin not in _EXECUTION_ORIGINS:
            raise RunInputError(f"origin must be one of {sorted(_EXECUTION_ORIGINS)}, got {self.origin!r}")
        if self.working_tree_state not in _WORKING_TREE_STATES:
            raise RunInputError(
                f"working_tree_state must be one of {sorted(_WORKING_TREE_STATES)}, "
                f"got {self.working_tree_state!r}"
            )
        if self.origin == "LOCAL":
            if self.working_tree_state == "NOT_APPLICABLE":
                raise RunInputError("working_tree_state must not be NOT_APPLICABLE for LOCAL origin")
        elif self.working_tree_state != "NOT_APPLICABLE":
            raise RunInputError(f"working_tree_state must be NOT_APPLICABLE for {self.origin} origin")


@dataclass(frozen=True, kw_only=True)
class RunProvenance:
    """Immutable Phase 0 domain value for the common Job Run provenance
    record (Architecture Baseline section 13; ADR-010). Enforces only
    static record-validity invariants -- no lifecycle transitions (ADR-010
    decision 9). Python None on an optional field represents absence for a
    future wire adapter, not a serialized JSON null (ADR-010)."""

    job_run_id: str
    job_type: JobType
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    trigger: str
    git_commit: str | None = None
    git_ref: str | None = None
    environment: str
    workflow_run_id: str | None = None
    error_summary: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        job_run_id = _validate_non_blank_string(self.job_run_id, "job_run_id")

        if self.job_type not in _JOB_TYPES:
            raise RunInputError(f"job_type must be one of {sorted(_JOB_TYPES)}, got {self.job_type!r}")
        if self.status not in _RUN_STATUSES:
            raise RunInputError(f"status must be one of {sorted(_RUN_STATUSES)}, got {self.status!r}")

        started_at = _ensure_utc(self.started_at, "started_at")
        finished_at = _ensure_utc(self.finished_at, "finished_at") if self.finished_at is not None else None

        trigger = _validate_non_blank_string(self.trigger, "trigger")
        environment = _validate_non_blank_string(self.environment, "environment")

        git_commit = _validate_optional_non_blank_string(self.git_commit, "git_commit")
        git_ref = _validate_optional_non_blank_string(self.git_ref, "git_ref")
        if (git_commit is None) != (git_ref is None):
            raise RunInputError("git_commit and git_ref must both be present or both be absent")

        workflow_run_id = _validate_optional_non_blank_string(self.workflow_run_id, "workflow_run_id")
        error_summary = _validate_optional_non_blank_string(self.error_summary, "error_summary")

        if self.status in _NO_FINISHED_AT_STATUSES:
            if finished_at is not None:
                raise RunInputError(f"finished_at must be absent while status is {self.status}")
        elif finished_at is None:
            raise RunInputError(f"finished_at is required once status is {self.status}")

        if finished_at is not None and finished_at < started_at:
            raise RunInputError("finished_at must not be before started_at")

        if self.status in _REQUIRES_ERROR_SUMMARY_STATUSES:
            if error_summary is None:
                raise RunInputError(f"error_summary is required while status is {self.status}")
        elif error_summary is not None:
            raise RunInputError(f"error_summary must be absent while status is {self.status}")

        metadata = _freeze_json_value(self.metadata, "metadata")
        if not isinstance(metadata, Mapping):
            raise RunInputError("metadata must be a JSON-compatible mapping")

        object.__setattr__(self, "job_run_id", job_run_id)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "finished_at", finished_at)
        object.__setattr__(self, "trigger", trigger)
        object.__setattr__(self, "git_commit", git_commit)
        object.__setattr__(self, "git_ref", git_ref)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "workflow_run_id", workflow_run_id)
        object.__setattr__(self, "error_summary", error_summary)
        object.__setattr__(self, "metadata", metadata)


def validate_run_provenance(provenance: RunProvenance, context: ExecutionContext) -> RunProvenance:
    """Pure contextual validation (ADR-010 decisions 6-8, 17-19): the
    origin-specific git/workflow_run_id rules that RunProvenance's own
    intrinsic validation cannot express on its own, since a bare
    RunProvenance carries no ExecutionContext. Does not mutate provenance or
    context, does not inspect system state, and returns the same provenance
    value on success."""
    if context.origin == "LOCAL":
        if provenance.workflow_run_id is not None:
            raise RunInputError("workflow_run_id must be absent for LOCAL execution")
        if context.working_tree_state in ("DIRTY", "UNKNOWN") and (
            provenance.git_commit is not None or provenance.git_ref is not None
        ):
            raise RunInputError(
                "git_commit and git_ref must be absent for LOCAL execution with a "
                f"{context.working_tree_state} working tree"
            )
    elif context.origin in ("CI", "GITHUB_ACTIONS"):
        if provenance.git_commit is None or provenance.git_ref is None:
            raise RunInputError(f"git_commit and git_ref are required for {context.origin} execution")
        if context.origin == "GITHUB_ACTIONS":
            if provenance.workflow_run_id is None:
                raise RunInputError("workflow_run_id is required for GITHUB_ACTIONS execution")
        elif provenance.workflow_run_id is not None:
            raise RunInputError("workflow_run_id must be absent for generic CI execution")
    else:
        raise RunInputError(f"unknown ExecutionOrigin: {context.origin!r}")

    return provenance
