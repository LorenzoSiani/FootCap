"""
Executable test matrix for the Temporal Engine (Task 0.4.3C section 12 /
Task 0.4.3D section 11).

The sys.path bootstrap below is required only because
engine/pyproject.toml (out of scope for this task) does not add
engine/src to pythonpath -- it only adds "tests" (for the existing
support.schema_loader import pattern used by engine/tests/contracts/).
Without it, footcap_engine would not be importable from this file.
"""
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from footcap_engine.temporal import (
    ClassificationResult,
    FactEvaluation,
    FactIneligibilityReason,
    MaterialFact,
    TemporalInputError,
    classify_material_facts,
    evaluate_fact,
)
from footcap_engine.temporal.evaluation import (
    _ensure_utc,
    _is_event_time_eligible,
    _is_knowledge_time_available,
)

CUTOFF = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
BEFORE = CUTOFF - timedelta(seconds=1)
AFTER = CUTOFF + timedelta(seconds=1)

FUTURE_EVENT = FactIneligibilityReason.FUTURE_EVENT
SOURCE_AVAILABILITY_UNKNOWN = FactIneligibilityReason.SOURCE_AVAILABILITY_UNKNOWN
SOURCE_AVAILABLE_AFTER_CUTOFF = FactIneligibilityReason.SOURCE_AVAILABLE_AFTER_CUTOFF


# ---- _ensure_utc ----

def test_ensure_utc_normalizes_non_utc_offset():
    non_utc = CUTOFF.astimezone(timezone(timedelta(hours=2)))
    normalized = _ensure_utc(non_utc)
    assert normalized == CUTOFF
    assert normalized.tzinfo == timezone.utc


def test_ensure_utc_rejects_naive():
    with pytest.raises(TemporalInputError):
        _ensure_utc(datetime(2026, 1, 1))


# ---- EVENT TIME (matrix items 1-3) ----

def test_event_at_before_cutoff_is_eligible():
    assert _is_event_time_eligible(BEFORE, CUTOFF) is True


def test_event_at_equal_cutoff_is_not_eligible():
    assert _is_event_time_eligible(CUTOFF, CUTOFF) is False


def test_event_at_after_cutoff_is_not_eligible():
    assert _is_event_time_eligible(AFTER, CUTOFF) is False


# ---- KNOWLEDGE TIME (matrix items 4-7) ----

def test_source_available_before_cutoff_is_available():
    assert _is_knowledge_time_available(BEFORE, CUTOFF) is True


def test_source_available_equal_cutoff_is_available():
    assert _is_knowledge_time_available(CUTOFF, CUTOFF) is True


def test_source_available_after_cutoff_is_not_available():
    assert _is_knowledge_time_available(AFTER, CUTOFF) is False


def test_source_available_none_is_not_available():
    assert _is_knowledge_time_available(None, CUTOFF) is False


# ---- NULL EVENT TIME (matrix items 8-10) ----

def test_event_at_none_with_known_availability():
    fact = MaterialFact("f1", event_at=None, source_available_at=BEFORE)
    result = evaluate_fact(fact, CUTOFF)
    assert result.event_time_eligible is True
    assert result.knowledge_time_available is True
    assert result.reasons == ()


def test_event_at_none_with_unknown_availability():
    fact = MaterialFact("f1", event_at=None, source_available_at=None)
    result = evaluate_fact(fact, CUTOFF)
    assert result.event_time_eligible is True
    assert result.knowledge_time_available is False
    assert result.reasons == (SOURCE_AVAILABILITY_UNKNOWN,)


def test_event_at_none_with_late_availability():
    fact = MaterialFact("f1", event_at=None, source_available_at=AFTER)
    result = evaluate_fact(fact, CUTOFF)
    assert result.event_time_eligible is True
    assert result.knowledge_time_available is False
    assert result.reasons == (SOURCE_AVAILABLE_AFTER_CUTOFF,)


# ---- MULTIPLE REASONS (matrix items 11-12) ----

def test_future_event_and_unknown_availability_preserve_both_reasons():
    fact = MaterialFact("f1", event_at=AFTER, source_available_at=None)
    result = evaluate_fact(fact, CUTOFF)
    assert result.event_time_eligible is False
    assert result.knowledge_time_available is False
    assert result.reasons == (FUTURE_EVENT, SOURCE_AVAILABILITY_UNKNOWN)


def test_future_event_and_late_availability_preserve_both_reasons():
    fact = MaterialFact("f1", event_at=AFTER, source_available_at=AFTER)
    result = evaluate_fact(fact, CUTOFF)
    assert result.reasons == (FUTURE_EVENT, SOURCE_AVAILABLE_AFTER_CUTOFF)


# ---- COLLECTIONS (matrix items 13-14) ----

def test_collection_with_one_unknown_fact_is_event_time_safe():
    facts = [
        MaterialFact("good-1", event_at=BEFORE, source_available_at=BEFORE),
        MaterialFact("unknown-1", event_at=BEFORE, source_available_at=None),
        MaterialFact("good-2", event_at=BEFORE, source_available_at=BEFORE),
    ]
    result = classify_material_facts(facts, CUTOFF)
    assert result.eligible is True
    assert result.temporal_classification == "EVENT_TIME_SAFE"
    assert [e.fact_id for e in result.fact_evaluations] == ["good-1", "unknown-1", "good-2"]
    assert result.fact_evaluations[1].reasons == (SOURCE_AVAILABILITY_UNKNOWN,)


def test_collection_with_future_event_is_ineligible_regardless_of_other_facts():
    facts = [
        MaterialFact("good-1", event_at=BEFORE, source_available_at=BEFORE),
        MaterialFact("future-1", event_at=AFTER, source_available_at=BEFORE),
    ]
    result = classify_material_facts(facts, CUTOFF)
    assert result.eligible is False
    assert result.temporal_classification is None


def test_collection_fully_verified():
    facts = [
        MaterialFact("good-1", event_at=BEFORE, source_available_at=BEFORE),
        MaterialFact("good-2", event_at=BEFORE, source_available_at=CUTOFF),
    ]
    result = classify_material_facts(facts, CUTOFF)
    assert result.eligible is True
    assert result.temporal_classification == "KNOWLEDGE_TIME_VERIFIED"


# ---- EMPTY SET (matrix item 15) ----

def test_empty_collection_raises():
    with pytest.raises(TemporalInputError):
        classify_material_facts([], CUTOFF)


# ---- DATETIME HANDLING (matrix items 16-21) ----

def test_utc_aware_datetime_accepted():
    fact = MaterialFact("f1", event_at=BEFORE, source_available_at=BEFORE)
    result = evaluate_fact(fact, CUTOFF)
    assert result.event_time_eligible is True


def test_aware_non_utc_datetime_normalized_and_semantically_equivalent():
    non_utc_before = BEFORE.astimezone(timezone(timedelta(hours=2)))
    fact_utc = MaterialFact("utc", event_at=BEFORE, source_available_at=BEFORE)
    fact_non_utc = MaterialFact("non-utc", event_at=non_utc_before, source_available_at=non_utc_before)

    assert fact_non_utc.event_at == fact_utc.event_at
    assert fact_non_utc.event_at.tzinfo == timezone.utc

    result_utc = evaluate_fact(fact_utc, CUTOFF)
    result_non_utc = evaluate_fact(fact_non_utc, CUTOFF)
    assert result_utc.event_time_eligible == result_non_utc.event_time_eligible
    assert result_utc.knowledge_time_available == result_non_utc.knowledge_time_available


def test_naive_event_at_rejected():
    with pytest.raises(TemporalInputError):
        MaterialFact("f1", event_at=datetime(2026, 1, 1), source_available_at=BEFORE)


def test_naive_source_available_at_rejected():
    with pytest.raises(TemporalInputError):
        MaterialFact("f1", event_at=BEFORE, source_available_at=datetime(2026, 1, 1))


def test_naive_prediction_cutoff_rejected():
    fact = MaterialFact("f1", event_at=BEFORE, source_available_at=BEFORE)
    with pytest.raises(TemporalInputError):
        evaluate_fact(fact, datetime(2026, 1, 1))


def test_wrong_timestamp_type_rejected():
    with pytest.raises(TemporalInputError):
        MaterialFact("f1", event_at="2026-01-01T00:00:00Z", source_available_at=None)


# ---- RESULT INVARIANTS ----

def test_result_invariant_ineligible_implies_no_classification():
    facts = [MaterialFact("f1", event_at=AFTER, source_available_at=BEFORE)]
    result = classify_material_facts(facts, CUTOFF)
    assert result.eligible is False
    assert result.temporal_classification is None


def test_result_invariant_eligible_implies_classification_present():
    facts = [MaterialFact("f1", event_at=BEFORE, source_available_at=BEFORE)]
    result = classify_material_facts(facts, CUTOFF)
    assert result.eligible is True
    assert result.temporal_classification is not None


# ==== Task 0.4.3F: required fixes from independent review ====

# ---- FIX 1: real datetime awareness ----

class _PseudoAwareTzinfo(tzinfo):
    """A tzinfo whose utcoffset() returns None -- proves _ensure_utc
    rejects pseudo-aware datetimes, not merely naive ones."""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "PSEUDO"


def test_pseudo_aware_datetime_rejected():
    pseudo_aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=_PseudoAwareTzinfo())
    with pytest.raises(TemporalInputError):
        _ensure_utc(pseudo_aware)


def test_fact_id_empty_string_rejected():
    with pytest.raises(TemporalInputError):
        MaterialFact("", event_at=BEFORE, source_available_at=BEFORE)


def test_fact_id_non_string_rejected():
    with pytest.raises(TemporalInputError):
        MaterialFact(123, event_at=BEFORE, source_available_at=BEFORE)


def test_source_available_at_wrong_type_rejected():
    with pytest.raises(TemporalInputError):
        MaterialFact("f1", event_at=BEFORE, source_available_at="2026-01-01T00:00:00Z")


def test_prediction_cutoff_wrong_type_rejected():
    fact = MaterialFact("f1", event_at=BEFORE, source_available_at=BEFORE)
    with pytest.raises(TemporalInputError):
        evaluate_fact(fact, "2026-01-01T12:00:00Z")


# ---- FIX 2: FactEvaluation invariants ----

def test_fact_evaluation_rejects_eligible_true_with_future_event_reason():
    with pytest.raises(TemporalInputError):
        FactEvaluation(
            "f1", event_time_eligible=True, knowledge_time_available=True, reasons=(FUTURE_EVENT,)
        )


def test_fact_evaluation_rejects_eligible_false_without_future_event_reason():
    with pytest.raises(TemporalInputError):
        FactEvaluation(
            "f1", event_time_eligible=False, knowledge_time_available=True, reasons=()
        )


def test_fact_evaluation_rejects_unknown_and_after_cutoff_together():
    with pytest.raises(TemporalInputError):
        FactEvaluation(
            "f1",
            event_time_eligible=True,
            knowledge_time_available=False,
            reasons=(SOURCE_AVAILABILITY_UNKNOWN, SOURCE_AVAILABLE_AFTER_CUTOFF),
        )


def test_fact_evaluation_rejects_duplicate_reasons():
    with pytest.raises(TemporalInputError):
        FactEvaluation(
            "f1", event_time_eligible=False, knowledge_time_available=True, reasons=(FUTURE_EVENT, FUTURE_EVENT)
        )


# ---- FIX 3: ClassificationResult invariants ----

def _good_evaluation(fact_id="good"):
    return FactEvaluation(fact_id, event_time_eligible=True, knowledge_time_available=True, reasons=())


def _unknown_evaluation(fact_id="unknown"):
    return FactEvaluation(
        fact_id, event_time_eligible=True, knowledge_time_available=False, reasons=(SOURCE_AVAILABILITY_UNKNOWN,)
    )


def _future_event_evaluation(fact_id="future"):
    return FactEvaluation(
        fact_id, event_time_eligible=False, knowledge_time_available=True, reasons=(FUTURE_EVENT,)
    )


def test_classification_result_rejects_eligible_true_with_none_classification():
    with pytest.raises(TemporalInputError):
        ClassificationResult(eligible=True, temporal_classification=None, fact_evaluations=(_good_evaluation(),))


def test_classification_result_rejects_eligible_false_with_non_none_classification():
    with pytest.raises(TemporalInputError):
        ClassificationResult(
            eligible=False,
            temporal_classification="EVENT_TIME_SAFE",
            fact_evaluations=(_future_event_evaluation(),),
        )


def test_classification_result_rejects_ktv_with_a_not_knowledge_time_available_fact():
    with pytest.raises(TemporalInputError):
        ClassificationResult(
            eligible=True,
            temporal_classification="KNOWLEDGE_TIME_VERIFIED",
            fact_evaluations=(_good_evaluation(), _unknown_evaluation()),
        )


def test_classification_result_rejects_ets_when_all_facts_are_knowledge_time_available():
    with pytest.raises(TemporalInputError):
        ClassificationResult(
            eligible=True,
            temporal_classification="EVENT_TIME_SAFE",
            fact_evaluations=(_good_evaluation("f1"), _good_evaluation("f2")),
        )


def test_classification_result_rejects_ineligible_when_every_fact_is_event_time_eligible():
    with pytest.raises(TemporalInputError):
        ClassificationResult(
            eligible=False,
            temporal_classification=None,
            fact_evaluations=(_good_evaluation(), _unknown_evaluation()),
        )


def test_classification_result_rejects_unknown_classification_value():
    """Not one of the 14 explicitly listed cases; added to directly cover
    Fix 3.F (no third classification value accepted), which the listed
    cases do not otherwise exercise."""
    with pytest.raises(TemporalInputError):
        ClassificationResult(
            eligible=True, temporal_classification="SOMETHING_ELSE", fact_evaluations=(_good_evaluation(),)
        )


# ==== Task 0.4.3H: empty ClassificationResult.fact_evaluations invariant ====

def test_classification_result_rejects_empty_fact_evaluations():
    with pytest.raises(TemporalInputError):
        ClassificationResult(
            eligible=True, temporal_classification="KNOWLEDGE_TIME_VERIFIED", fact_evaluations=()
        )


def test_classification_result_accepts_valid_non_empty_ktv_construction():
    evaluation = FactEvaluation(
        fact_id="f1", event_time_eligible=True, knowledge_time_available=True, reasons=()
    )
    result = ClassificationResult(
        eligible=True, temporal_classification="KNOWLEDGE_TIME_VERIFIED", fact_evaluations=(evaluation,)
    )
    assert result.eligible is True
    assert result.temporal_classification == "KNOWLEDGE_TIME_VERIFIED"
    assert result.fact_evaluations == (evaluation,)
