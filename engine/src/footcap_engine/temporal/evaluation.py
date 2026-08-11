"""
Temporal Engine implementation (Architecture Baseline section 5).

event_at = None means the event-time dimension is NOT APPLICABLE to a
fact; the event-time comparison is skipped and the fact is treated as
event-time eligible on that basis. It must never be read as "unknown
event time".

source_available_at = None means UNKNOWN availability (Architecture
Baseline section 5.2; ADR-009 decision 12). It always prevents
Knowledge-Time Verified classification but never by itself prevents
Event-Time Safe classification.

No database, network, or filesystem access. No persistence. No global
mutable state. Every function here is pure with respect to its
arguments.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Sequence, get_args

# The cross-language source of truth for these two values remains
# packages/contracts/schemas/definitions.schema.json#/$defs/TemporalClassification.
# This is a plain typing.Literal, not a hand-authored Enum, so it introduces
# no second, competing definition -- see engine/tests/temporal/test_contract_drift.py.
TemporalClassification = Literal["EVENT_TIME_SAFE", "KNOWLEDGE_TIME_VERIFIED"]

# Derived from the Literal above rather than hand-typed a second time, so
# ClassificationResult's own validation below cannot itself drift from it.
_VALID_CLASSIFICATIONS = frozenset(get_args(TemporalClassification))


class TemporalInputError(ValueError):
    """Malformed input to the Temporal Engine. Never raised for a valid
    but temporally ineligible domain value (see evaluate_fact)."""


class FactIneligibilityReason(str, Enum):
    """Engine-owned diagnostic reasons. Not a mirror of any shared
    contract -- no corresponding definition exists under
    packages/contracts/schemas/."""

    FUTURE_EVENT = "FUTURE_EVENT"
    SOURCE_AVAILABILITY_UNKNOWN = "SOURCE_AVAILABILITY_UNKNOWN"
    SOURCE_AVAILABLE_AFTER_CUTOFF = "SOURCE_AVAILABLE_AFTER_CUTOFF"


def _ensure_utc(value: datetime) -> datetime:
    """Reject non-datetime input and naive/pseudo-aware datetimes;
    normalize any genuinely timezone-aware datetime to UTC. A datetime is
    only considered aware when tzinfo is set AND utcoffset() actually
    resolves to a real offset -- a tzinfo implementation whose utcoffset()
    returns None is not usable and must be rejected the same as naive."""
    if not isinstance(value, datetime):
        raise TemporalInputError(f"expected a datetime.datetime, got {type(value)!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TemporalInputError("naive datetime is not accepted; a timezone-aware datetime is required")
    return value.astimezone(timezone.utc)


def _is_event_time_eligible(event_at: datetime, prediction_cutoff: datetime) -> bool:
    """event_at < prediction_cutoff, strict. Equality is not eligible."""
    return event_at < prediction_cutoff


def _is_knowledge_time_available(source_available_at: datetime | None, prediction_cutoff: datetime) -> bool:
    """source_available_at <= prediction_cutoff, non-strict. Equality is
    valid. None (UNKNOWN) always evaluates to False -- it is a normal,
    evaluated domain input here, not a signal to skip this check."""
    if source_available_at is None:
        return False
    return source_available_at <= prediction_cutoff


@dataclass(frozen=True)
class MaterialFact:
    """The minimum representation of a material source fact (Architecture
    Baseline section 5.3) needed for temporal evaluation -- identity plus
    the two temporal fields. Not a general football source-data model."""

    fact_id: str
    event_at: datetime | None
    source_available_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.fact_id, str) or not self.fact_id:
            raise TemporalInputError("fact_id must be a non-empty string")
        if self.event_at is not None:
            object.__setattr__(self, "event_at", _ensure_utc(self.event_at))
        if self.source_available_at is not None:
            object.__setattr__(self, "source_available_at", _ensure_utc(self.source_available_at))


@dataclass(frozen=True)
class FactEvaluation:
    """Per-fact result of evaluating one MaterialFact against one
    prediction_cutoff. __post_init__ enforces internal consistency so a
    contradictory FactEvaluation cannot be manually constructed."""

    fact_id: str
    event_time_eligible: bool
    knowledge_time_available: bool
    reasons: tuple[FactIneligibilityReason, ...]

    def __post_init__(self) -> None:
        reasons = self.reasons
        if len(set(reasons)) != len(reasons):
            raise TemporalInputError("FactEvaluation.reasons must not contain duplicates")

        has_future_event = FactIneligibilityReason.FUTURE_EVENT in reasons
        has_unknown = FactIneligibilityReason.SOURCE_AVAILABILITY_UNKNOWN in reasons
        has_late = FactIneligibilityReason.SOURCE_AVAILABLE_AFTER_CUTOFF in reasons

        if has_unknown and has_late:
            raise TemporalInputError(
                "FactEvaluation.reasons must not contain both SOURCE_AVAILABILITY_UNKNOWN "
                "and SOURCE_AVAILABLE_AFTER_CUTOFF"
            )
        if self.event_time_eligible != (not has_future_event):
            raise TemporalInputError(
                "FactEvaluation.event_time_eligible must be False if and only if "
                "FUTURE_EVENT is present in reasons"
            )
        if self.knowledge_time_available != (not (has_unknown or has_late)):
            raise TemporalInputError(
                "FactEvaluation.knowledge_time_available must be False if and only if "
                "SOURCE_AVAILABILITY_UNKNOWN or SOURCE_AVAILABLE_AFTER_CUTOFF is present in reasons"
            )


@dataclass(frozen=True)
class ClassificationResult:
    """Collection-level result of classify_material_facts. eligible is
    False if and only if temporal_classification is None.
    __post_init__ enforces internal consistency so a contradictory
    ClassificationResult cannot be manually constructed."""

    eligible: bool
    temporal_classification: TemporalClassification | None
    fact_evaluations: tuple[FactEvaluation, ...]

    def __post_init__(self) -> None:
        if len(self.fact_evaluations) == 0:
            raise TemporalInputError(
                "ClassificationResult.fact_evaluations must not be empty; a classification "
                "represents a complete, non-empty set of evaluated material facts"
            )

        classification = self.temporal_classification
        if classification is not None and classification not in _VALID_CLASSIFICATIONS:
            raise TemporalInputError(
                "ClassificationResult.temporal_classification must be None or one of "
                f"{sorted(_VALID_CLASSIFICATIONS)}"
            )
        if not self.eligible and classification is not None:
            raise TemporalInputError(
                "ClassificationResult.eligible is False but temporal_classification is not None"
            )
        if self.eligible and classification is None:
            raise TemporalInputError(
                "ClassificationResult.eligible is True but temporal_classification is None"
            )

        all_event_time_eligible = all(e.event_time_eligible for e in self.fact_evaluations)
        all_knowledge_time_available = all(e.knowledge_time_available for e in self.fact_evaluations)

        if not self.eligible and all_event_time_eligible:
            raise TemporalInputError(
                "ClassificationResult.eligible is False but every fact_evaluations entry "
                "is event-time eligible"
            )
        if classification == "KNOWLEDGE_TIME_VERIFIED" and not (
            all_event_time_eligible and all_knowledge_time_available
        ):
            raise TemporalInputError(
                "KNOWLEDGE_TIME_VERIFIED requires every fact_evaluations entry to be "
                "event-time eligible and knowledge-time available"
            )
        if classification == "EVENT_TIME_SAFE" and not (
            all_event_time_eligible and not all_knowledge_time_available
        ):
            raise TemporalInputError(
                "EVENT_TIME_SAFE requires every fact_evaluations entry to be event-time "
                "eligible and at least one to be not knowledge-time available"
            )


def evaluate_fact(fact: MaterialFact, prediction_cutoff: datetime) -> FactEvaluation:
    """Evaluate one MaterialFact against one prediction_cutoff. Pure; no
    side effects. Preserves every applicable diagnostic reason, in the
    canonical order FUTURE_EVENT, SOURCE_AVAILABILITY_UNKNOWN,
    SOURCE_AVAILABLE_AFTER_CUTOFF -- a fact may carry more than one."""
    cutoff = _ensure_utc(prediction_cutoff)

    if fact.event_at is None:
        event_time_eligible = True
    else:
        event_time_eligible = _is_event_time_eligible(fact.event_at, cutoff)

    knowledge_time_available = _is_knowledge_time_available(fact.source_available_at, cutoff)

    reasons: list[FactIneligibilityReason] = []
    if not event_time_eligible:
        reasons.append(FactIneligibilityReason.FUTURE_EVENT)
    if not knowledge_time_available:
        if fact.source_available_at is None:
            reasons.append(FactIneligibilityReason.SOURCE_AVAILABILITY_UNKNOWN)
        else:
            reasons.append(FactIneligibilityReason.SOURCE_AVAILABLE_AFTER_CUTOFF)

    return FactEvaluation(
        fact_id=fact.fact_id,
        event_time_eligible=event_time_eligible,
        knowledge_time_available=knowledge_time_available,
        reasons=tuple(reasons),
    )


def classify_material_facts(facts: Sequence[MaterialFact], prediction_cutoff: datetime) -> ClassificationResult:
    """Classify a complete collection of material source facts for one
    prediction_cutoff (Architecture Baseline section 5.5).

    The full input set is always evaluated in a single pass. Facts must
    never be removed and the reduced collection reclassified by a caller
    -- that would launder a genuine future-information leak into an
    apparently clean classification. Callers must reject the entire
    computation when eligible is False.
    """
    if len(facts) == 0:
        raise TemporalInputError("classify_material_facts requires at least one material fact")

    cutoff = _ensure_utc(prediction_cutoff)
    evaluations = tuple(evaluate_fact(fact, cutoff) for fact in facts)

    eligible = all(evaluation.event_time_eligible for evaluation in evaluations)
    classification: TemporalClassification | None
    if not eligible:
        classification = None
    elif all(evaluation.knowledge_time_available for evaluation in evaluations):
        classification = "KNOWLEDGE_TIME_VERIFIED"
    else:
        classification = "EVENT_TIME_SAFE"

    return ClassificationResult(
        eligible=eligible,
        temporal_classification=classification,
        fact_evaluations=evaluations,
    )
