"""
Guards against drift between the Run Engine's RunStatus/JobType Literal
aliases and the shared contract's RunStatus/JobType enums
(packages/contracts/schemas/definitions.schema.json and
packages/contracts/schemas/run-provenance.schema.json respectively). Both
are represented as plain typing.Literal in Python -- not hand-authored
Enums -- specifically so JSON Schema remains the single source of truth
(mirrors engine/tests/temporal/test_contract_drift.py); this test is the
mechanism that makes that safe.

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath.
"""
import sys
import typing
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from footcap_engine.runs import JobType, RunStatus
from support.schema_loader import load_schema


def test_run_status_matches_shared_contract():
    schema_values = set(load_schema("definitions.schema.json")["$defs"]["RunStatus"]["enum"])
    engine_values = set(typing.get_args(RunStatus))
    assert engine_values == schema_values


def test_job_type_matches_shared_contract():
    schema_values = set(load_schema("run-provenance.schema.json")["$defs"]["JobType"]["enum"])
    engine_values = set(typing.get_args(JobType))
    assert engine_values == schema_values
