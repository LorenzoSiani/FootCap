"""
Phase 0.4.2 smoke test: the prediction.schema.json conditional
publication_state rule (Task 0.4.1B; resolved in Task 0.4.1A) enforced by
a real jsonschema Draft202012Validator. This deliberately does not reuse
the hand-built evaluator written for the Task 0.4.1C audit -- that
evaluator only proved the rule's *shape* by reading it out of the file;
this test proves a real validator actually enforces it at runtime.
"""
import copy
import json
from pathlib import Path

import pytest

from support.schema_loader import validator_for

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "prediction"
BASE_FIXTURE = json.loads((FIXTURES_DIR / "valid_production_published.json").read_text(encoding="utf-8"))

REMOVE = object()


def _variant(**overrides):
    """Deep-copy BASE_FIXTURE, setting each override key's value, or
    removing the key entirely if its value is the REMOVE sentinel."""
    fixture = copy.deepcopy(BASE_FIXTURE)
    for key, value in overrides.items():
        if value is REMOVE:
            fixture.pop(key, None)
        else:
            fixture[key] = value
    return fixture


CASES = [
    pytest.param(
        _variant(evaluation_context="PRODUCTION", publication_state=REMOVE),
        False,
        id="production-without-publication-state",
    ),
    pytest.param(
        _variant(evaluation_context="PRODUCTION", publication_state="PUBLISHED"),
        True,
        id="production-with-published",
    ),
    pytest.param(
        _variant(evaluation_context="BACKTEST", publication_state=REMOVE),
        True,
        id="backtest-without-publication-state",
    ),
    pytest.param(
        _variant(evaluation_context="BACKTEST", publication_state="PUBLISHED"),
        False,
        id="backtest-with-publication-state",
    ),
    pytest.param(
        _variant(evaluation_context="EXPERIMENT", publication_state=REMOVE),
        True,
        id="experiment-without-publication-state",
    ),
    pytest.param(
        _variant(evaluation_context="EXPERIMENT", publication_state="PUBLISHED"),
        False,
        id="experiment-with-publication-state",
    ),
    pytest.param(
        _variant(evaluation_context="PRODUCTION", publication_state=None),
        False,
        id="publication-state-null",
    ),
]


@pytest.mark.parametrize("fixture, expected_valid", CASES)
def test_prediction_publication_state_conditional(fixture, expected_valid):
    validator = validator_for("prediction.schema.json")
    assert validator.is_valid(fixture) is expected_valid
