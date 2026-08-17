"""
Public boundary for the FootCap Temporal Engine (Architecture Baseline
section 5). Only the names re-exported here are part of the stable
contract other engine modules may depend on; everything else in
evaluation.py is a private implementation detail.
"""
from .evaluation import (
    ClassificationResult,
    FactEvaluation,
    FactIneligibilityReason,
    MaterialFact,
    TemporalClassification,
    TemporalInputError,
    classify_material_facts,
    evaluate_fact,
)

__all__ = [
    "ClassificationResult",
    "FactEvaluation",
    "FactIneligibilityReason",
    "MaterialFact",
    "TemporalClassification",
    "TemporalInputError",
    "classify_material_facts",
    "evaluate_fact",
]
