"""
Guards against drift between the Temporal Engine's TemporalClassification
Literal and the shared contract's TemporalClassification enum
(packages/contracts/schemas/definitions.schema.json). This test exists
because TemporalClassification is represented as a plain typing.Literal
in Python -- not a hand-authored Enum -- specifically so JSON Schema
remains the single source of truth (Task 0.4.3C section 13); this test
is the mechanism that makes that safe.

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

from footcap_engine.temporal import TemporalClassification
from support.schema_loader import load_schema


def test_temporal_classification_matches_shared_contract():
    schema_values = set(
        load_schema("definitions.schema.json")["$defs"]["TemporalClassification"]["enum"]
    )
    engine_values = set(typing.get_args(TemporalClassification))
    assert engine_values == schema_values
