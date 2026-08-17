"""
Phase 0.4.2 smoke tests: prove the JSON Schema test infrastructure itself
works against packages/contracts/schemas/ -- schema loading, validator
construction, and cross-file $ref resolution. This is infrastructure
validation, not a Prediction-lifecycle or temporal domain-invariant test
suite; those are deferred until the corresponding engine/src/footcap_engine
domain modules exist (Task 0.4.1 test-design review).
"""
import json
from pathlib import Path

from support.schema_loader import load_schema, schemas_dir, validator_for

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "prediction"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_known_schema_document_loads():
    schema = load_schema("prediction.schema.json")
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith("prediction.schema.json")


def test_all_contract_schema_files_are_loadable():
    filenames = {path.name for path in schemas_dir().glob("*.schema.json")}
    assert "prediction.schema.json" in filenames
    assert "definitions.schema.json" in filenames
    for filename in filenames:
        schema = load_schema(filename)
        assert "$schema" in schema
        assert "$id" in schema


def test_valid_prediction_payload_is_accepted():
    fixture = _load_fixture("valid_production_published.json")
    validator = validator_for("prediction.schema.json")
    assert validator.is_valid(fixture)


def test_invalid_prediction_payload_missing_required_field_is_rejected():
    fixture = _load_fixture("invalid_missing_created_at.json")
    validator = validator_for("prediction.schema.json")
    assert not validator.is_valid(fixture)


def test_cross_file_ref_to_definitions_is_actually_resolved():
    """evaluation_context is validated only via the cross-file $ref
    "definitions.schema.json#/$defs/EvaluationContext". If cross-file
    $ref resolution were broken, this enum constraint would never be
    applied and the clearly-invalid value below would pass."""
    fixture = _load_fixture("invalid_bad_evaluation_context.json")
    validator = validator_for("prediction.schema.json")
    errors = list(validator.iter_errors(fixture))
    assert not validator.is_valid(fixture)
    assert any(
        list(error.path) == ["evaluation_context"] and error.validator == "enum"
        for error in errors
    ), "expected an 'enum' violation on evaluation_context, proving the cross-file EvaluationContext $ref was resolved and applied"
