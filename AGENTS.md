# FootCap — Agent Instructions

## Project

FootCap is a production-oriented football intelligence platform.

The project combines:

- football data
- statistical models
- probabilistic predictions
- AI-powered analysis
- live football information

The initial competition is Serie A.

---

## General Principles

Before modifying the project:

1. Understand the existing architecture.
2. Read the relevant documentation.
3. Avoid unnecessary changes.
4. Do not introduce new dependencies without justification.
5. Do not make architectural changes silently.
6. Keep changes small and reviewable.
7. Prefer maintainable and testable solutions.
8. Never expose secrets or credentials.
9. Never commit API keys.
10. Do not modify unrelated files.

---

## Architecture

The target architecture separates:

- frontend
- application/API services
- database
- data ingestion
- prediction engine
- AI engine
- automation

The frontend must not contain core prediction logic.

The prediction engine must remain independent from the AI layer.

The AI must interpret FootCap data and model outputs rather than inventing
numerical predictions independently.

---

## Data Integrity

Football data is a critical part of FootCap.

Never fabricate:

- matches
- statistics
- probabilities
- team data
- player data
- live information

Historical prediction systems must avoid data leakage.

Predictions must only use information that would have been available at
the time of prediction.

---

## Database

Database changes must be implemented through version-controlled
migrations.

Do not manually alter production database structures without creating
the corresponding migration.

Never hardcode database credentials.

---

## AI

AI-generated analysis must be grounded in FootCap data.

When an AI feature requires factual football information, it should
retrieve the required data through an appropriate FootCap service or
tool.

The AI should distinguish between:

- factual data
- model outputs
- interpretation
- uncertainty

---

## Security

Never commit:

- API keys
- passwords
- tokens
- private credentials
- `.env` files
- service-role secrets

Use environment variables.

---

## Git

Use clear and descriptive commits.

Avoid mixing unrelated changes into the same commit.

Before committing:

- inspect changed files
- review the diff
- run relevant tests
- verify that no secrets are included

---

## Documentation

Important architectural decisions must be documented.

Documentation belongs in:

`docs/architecture/`

`docs/product/`

`docs/decisions/`

`docs/research/`

Do not allow important architectural decisions to exist only inside
conversation history.

---

## Change Logger

FootCap will include an automatic change logging system.

The system must eventually record changes regardless of whether they
were made by:

- ChatGPT
- Codex
- Claude Code
- another IDE
- another coding tool
- a human developer

The logger should detect changes through filesystem and/or Git
information rather than relying exclusively on a specific AI tool.

Do not falsely identify the source of a change.

If the source cannot be reliably determined, use:

`unknown`

---

## Current Project Phase

The project is currently in the architecture phase.

Do NOT implement the complete FootCap application unless explicitly
requested.

At the beginning of the project, agents should:

1. analyze
2. identify risks
3. identify missing decisions
4. propose improvements
5. wait for architectural decisions before implementing major systems