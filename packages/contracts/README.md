# Shared contracts

This directory is the single boundary for shared cross-language FootCap contracts.

## Source of truth

JSON Schema (draft 2020-12) files under `schemas/` are the single source of truth for every shared shape. TypeScript types and Python/Pydantic representations are derived/generated/validated from these schema files; they are never authored a second time by hand (ADR-009).

`engine/src/footcap_engine/contracts/` holds Python Engine-only representations and must not duplicate anything defined here.

## What these schemas validate

JSON Schema validates structural shape: field presence, types, and closed enum values (e.g. `temporal_classification`, `publication_state`).

It does **not** validate cross-field or cross-record invariants -- for example, `event_at < prediction_cutoff`, `source_available_at <= prediction_cutoff` for Knowledge-Time Verified data, the one-PUBLISHED-per-match uniqueness rule, valid publication lifecycle transitions, or foreign-key/lineage existence across records. Those are enforced by Engine/domain logic and the database, not by these schemas. Each schema's `description` documents the specific limitations that apply to it.

## Status

These schemas are V1 Phase 0 implementation artifacts governed by [ADR-009](../../docs/decisions/ADR-009-contracts-foundation.md). `docs/architecture/FOOTCAP_ARCHITECTURE_V1.2.1.md` remains the authoritative, frozen Architecture Baseline; nothing here reinterprets or extends it.
