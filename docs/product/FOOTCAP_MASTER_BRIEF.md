# FOOTCAP — MASTER PROJECT BRIEF

**Document version:** 0.1  
**Status:** Architecture / Discovery  
**Project:** FootCap  
**Initial market:** Football analytics  
**Initial competition:** Serie A

---

# 1. PROJECT VISION

FootCap is a football intelligence platform designed to combine:

- football data
- statistical analysis
- probabilistic prediction models
- historical backtesting
- live match information
- AI-powered football analysis
- AI-powered natural language interaction

FootCap should NOT be positioned as a traditional bookmaker-style
prediction website.

The intended product direction is closer to a:

> Football Intelligence Platform

The product should communicate data, probability, analysis and
uncertainty clearly.

---

# 2. CORE PRODUCT PHILOSOPHY

The fundamental FootCap pipeline is:

DATA → MODEL → PROBABILITY → AI → USER

The statistical model is responsible for producing numerical
probabilities.

The AI layer is responsible for interpreting FootCap data and model
outputs.

The AI must not independently invent football predictions.

The AI should be grounded in real data retrieved from FootCap services.

---

# 3. INITIAL PRODUCT SCOPE

The first version will focus on Serie A.

The initial product should eventually provide:

- Serie A fixtures
- historical matches
- team statistics
- team form
- match statistics
- probabilistic predictions
- model performance metrics
- historical backtesting
- match analysis
- AI Analyst
- AI Assistant
- live match information

Additional competitions should be possible in the future without
requiring a complete architectural rewrite.

---

# 4. TARGET USERS

The initial target user is a football fan interested in:

- statistics
- football analysis
- probabilities
- match previews
- historical performance
- data-driven decision making

Potential future user segments may include:

- advanced football analysts
- fantasy football users
- bettors
- football content creators
- sports data enthusiasts

These segments must be validated before being treated as primary
product requirements.

---

# 5. PRODUCT DIFFERENTIATION

FootCap should differentiate itself through the combination of:

1. real football data
2. transparent statistical models
3. measurable historical performance
4. AI-powered interpretation
5. explainable predictions
6. live intelligence

The product should avoid becoming simply:

> "An AI chatbot that predicts football matches."

The core value should come from the FootCap data and prediction engine.

AI is an additional intelligence layer.

---

# 6. INITIAL DATA SOURCE

The initial football data provider is:

API-Football.

The system should be designed so that the data provider can potentially
be replaced or supplemented in the future.

External data should pass through a FootCap data ingestion layer before
being consumed by the rest of the application.

Conceptual pipeline:

API-Football
    ↓
Data ingestion
    ↓
Validation
    ↓
Normalization
    ↓
Database
    ↓
Application / Prediction Engine

---

# 7. DATA ENGINE REQUIREMENTS

The data ingestion system should:

- retrieve football data from external APIs
- validate incoming data
- normalize external formats
- store data in the FootCap database
- avoid duplicate records
- support repeatable ingestion
- support historical imports
- support future incremental updates

Where practical, raw external data should be preserved so that it can
be reprocessed later.

Ingestion should be idempotent whenever possible.

---

# 8. DATABASE

The initial database technology is:

Supabase / PostgreSQL.

Potential domain entities include:

- competitions
- seasons
- teams
- players
- venues
- matches
- match_events
- match_statistics
- team_form
- team_strength
- predictions
- prediction_results
- model_runs
- backtests
- ai_analyses
- users
- subscriptions
- favorites

This list is NOT the final database schema.

The database schema must be designed and reviewed before implementation.

Database changes must use version-controlled migrations.

---

# 9. PREDICTION ENGINE

The initial statistical prediction model will be:

Dixon-Coles.

The model should initially investigate factors such as:

- historical results
- home advantage
- attacking strength
- defensive strength
- opponent strength
- time decay
- expected goals
- other statistically justified variables

The model should produce probabilities such as:

- home win
- draw
- away win

Example only:

Home: 57.4%
Draw: 24.1%
Away: 18.5%

These numbers are illustrative and must never be hardcoded.

---

# 10. MODEL ARCHITECTURE

The prediction engine must remain independent from the frontend and
AI layer.

Conceptually:

Historical data
    ↓
Feature preparation
    ↓
Model
    ↓
Expected goals
    ↓
Probability distribution
    ↓
Prediction result

The architecture should make it possible to replace Dixon-Coles with
another model in the future without rewriting the entire application.

Potential future models may include:

- Poisson variants
- Elo-based systems
- gradient boosting
- ensemble models
- other statistically validated approaches

These are future possibilities, not initial requirements.

---

# 11. BACKTESTING

Backtesting is a mandatory part of the project.

The initial evaluation should use approximately three Serie A seasons.

The system should support historical simulation where each prediction
uses only information that would have been available at that point in
time.

Avoiding data leakage is a critical requirement.

Potential evaluation metrics include:

- Accuracy
- Log Loss
- Brier Score
- calibration
- sample size

ROI may be investigated as an additional metric but must not be treated
as proof of model quality.

Model results should be reproducible.

Model runs should ideally be identifiable and versioned.

---

# 12. PREDICTION TRANSPARENCY

FootCap should not only display:

> Inter 57%

It should eventually be possible to understand why the model produced
that probability.

Potential explanatory factors include:

- team strength
- recent form
- home advantage
- offensive strength
- defensive strength
- expected goals
- relevant historical information

The exact explanation methodology must be designed carefully so that
the explanation does not falsely imply causal relationships.

---

# 13. AI ENGINE

AI is a core product component but is NOT the source of numerical
predictions.

The AI layer should retrieve real FootCap information and interpret it.

Conceptual architecture:

User
 ↓
AI Assistant
 ↓
FootCap tools/services
 ↓
Database / Prediction Engine
 ↓
Structured data
 ↓
AI response

Potential tools include:

- get_match
- get_prediction
- get_team_stats
- get_team_form
- get_head_to_head
- get_live_match
- get_model_explanation
- compare_teams

The final tool list must be designed during the architecture phase.

---

# 14. AI ANALYST

The AI Analyst should eventually appear within individual match pages.

Example:

INTER vs MILAN

FootCap Prediction

Home: 57%
Draw: 24%
Away: 19%

AI Analyst

The AI explains the main factors behind the prediction using real
FootCap data.

The AI should distinguish between:

- factual information
- model output
- interpretation
- uncertainty

The AI must not fabricate statistics.

---

# 15. AI ASSISTANT

FootCap should eventually provide a general AI Assistant.

Example user query:

"Which matches this weekend have the highest home-win probability?"

The assistant should:

1. understand the request
2. determine which FootCap data is required
3. retrieve the relevant data
4. retrieve model predictions
5. analyze the results
6. provide an understandable answer
7. communicate uncertainty when appropriate

The assistant should use tools rather than relying solely on the LLM's
internal knowledge.

---

# 16. LIVE INTELLIGENCE

A future phase should introduce live match intelligence.

Conceptual flow:

API-Football live data
    ↓
Live data service
    ↓
FootCap database / state
    ↓
Prediction / analysis layer
    ↓
AI Analyst
    ↓
User

Live statistics must never be fabricated.

The architecture should account for data freshness, update frequency,
caching and failure scenarios.

---

# 17. FRONTEND

The initial frontend technology is:

- Next.js
- TypeScript
- Tailwind CSS

The visual direction should be:

- professional
- analytical
- modern
- data-driven
- clean
- information-rich

The interface should feel closer to:

- sports analytics
- financial dashboards
- intelligence platforms

than to a traditional bookmaker.

The previously selected visual direction is:

Direction 3.

---

# 18. FRONTEND RESPONSIBILITIES

The frontend should primarily be responsible for:

- presentation
- interaction
- navigation
- filtering
- visualization
- user input

Core business logic should not be duplicated inside the frontend.

Prediction logic should remain in the prediction engine.

AI orchestration should remain in the appropriate application/backend
layer.

---

# 19. MOBILE

Flutter may be introduced in a future phase.

The backend architecture should therefore avoid coupling the business
logic exclusively to the web frontend.

Future clients should be able to consume FootCap services through
well-defined APIs.

---

# 20. DEVELOPMENT AI STACK

The project will use:

### ChatGPT

Primary role:

- product architecture
- reasoning
- planning
- technical analysis
- specifications
- documentation
- architecture review

### OpenAI Codex

Primary coding agent.

Potential responsibilities:

- implementation
- refactoring
- tests
- repository operations
- debugging
- technical execution

Codex has not yet been configured for the project.

### Claude Code

Secondary coding/review agent.

Potential responsibilities:

- implementation
- debugging
- refactoring
- code review
- security review
- alternative technical approaches

The agents must share the same project vision and documentation.

No individual agent has unilateral authority over major architectural
decisions.

---

# 21. DEVELOPMENT WORKFLOW

The intended workflow is:

Product / Architecture
        ↓
Specification
        ↓
AI analysis
        ↓
Architecture decision
        ↓
Implementation
        ↓
Testing
        ↓
Code review
        ↓
Commit
        ↓
GitHub
        ↓
Deployment

Major architectural decisions should be documented.

---

# 22. CHANGE LOG SYSTEM

FootCap must have an automatic change logging system.

The system should record project modifications regardless of whether
they are made using:

- ChatGPT
- Codex
- Claude Code
- VS Code
- another IDE
- another coding agent
- manual editing

The system should detect changes through filesystem and/or Git
information rather than depending exclusively on a specific AI platform.

Conceptual architecture:

File change
    ↓
Change watcher
    ↓
Diff
    ↓
Git metadata
    ↓
Change event
    ↓
Machine-readable log

The raw format should preferably be JSONL.

Each event may contain:

- timestamp
- source
- author
- files
- change type
- branch
- commit
- session
- tests
- status
- description

If the source cannot be reliably identified:

source = unknown

The system must never fabricate attribution.

A human-readable CHANGELOG.md may later be generated from the raw log.

The audit system should be protected against accidental modification
by coding agents.

The exact implementation of the logger is an architectural decision
that must be evaluated before development.

---

# 23. REPOSITORY STRUCTURE

The intended repository is a monorepo.

Target structure:

footcap/

├── apps/
│   └── web/

├── services/
│   ├── data-ingestion/
│   ├── prediction-engine/
│   └── ai-engine/

├── packages/
│   ├── types/
│   ├── config/
│   └── validation/

├── supabase/
│   ├── migrations/
│   ├── seed/
│   └── functions/

├── scripts/

├── tools/
│   └── change-logger/

├── tests/

├── docs/
│   ├── architecture/
│   ├── product/
│   ├── decisions/
│   └── research/

├── logs/

├── .github/
│   └── workflows/

├── AGENTS.md
├── CLAUDE.md
├── README.md
└── package.json

This is the TARGET structure, not an instruction to create every
directory immediately.

---

# 24. DEPLOYMENT

Initial target:

Frontend:
Vercel

Database:
Supabase

Prediction / data services:
Python-based services/workers

DigitalOcean should NOT be introduced unless there is a clear technical
reason.

Avoid unnecessary infrastructure during the MVP.

---

# 25. SECURITY

The project must never commit:

- API keys
- passwords
- authentication secrets
- service-role keys
- private credentials
- .env files

Environment variables must be used for secrets.

Security must be considered from the beginning.

---

# 26. OBSERVABILITY

The architecture should eventually support:

- application logging
- error tracking
- model run tracking
- data ingestion monitoring
- AI request monitoring
- API failure monitoring
- prediction reproducibility

The exact observability stack is not yet decided.

---

# 27. INITIAL DEVELOPMENT PHASES

The intended development roadmap is:

PHASE 0 — Foundation

- repository
- documentation
- development rules
- change logger architecture
- CI foundation

PHASE 1 — Database Architecture

- domain model
- schema
- migrations
- constraints
- indexes

PHASE 2 — Data Engine

- API-Football integration
- historical import
- validation
- normalization
- ingestion jobs

PHASE 3 — Prediction Engine

- feature preparation
- Dixon-Coles
- probability generation
- model versioning

PHASE 4 — Backtesting

- historical simulation
- evaluation metrics
- calibration
- reproducibility
- leakage prevention

PHASE 5 — Application API

- matches
- teams
- competitions
- statistics
- predictions

PHASE 6 — Web Application

- dashboard
- match pages
- team pages
- competition pages
- statistics
- prediction visualization

PHASE 7 — AI Analyst

- structured tools
- model explanation
- match analysis

PHASE 8 — AI Assistant

- natural language queries
- tool calling
- data retrieval
- analysis

PHASE 9 — Live Intelligence

- live data
- live state
- live analysis

PHASE 10 — Accounts / Monetization

- authentication
- subscriptions
- free/pro features

PHASE 11 — Mobile

- Flutter application

The phases may be modified after architecture review.

---

# 28. CURRENT PROJECT STATUS

Current status:

Architecture / Discovery.

The GitHub repository has been initialized.

No production application code should be created yet.

---

# 29. CURRENT OBJECTIVE

The immediate objective is NOT to build FootCap.

The immediate objective is to validate the architecture.

The project should now be independently analyzed by:

- Codex
- Claude Code

Both agents should receive this document and the repository context.

---

# 30. INSTRUCTIONS FOR THE ARCHITECTURE REVIEW

At this stage, DO NOT implement FootCap.

DO NOT create the complete application.

DO NOT install large numbers of dependencies.

DO NOT create the complete database schema.

DO NOT implement the prediction engine.

DO NOT implement the AI engine.

Instead:

1. Read the repository.
2. Read AGENTS.md.
3. Read CLAUDE.md where applicable.
4. Read this Master Brief.
5. Analyze the proposed architecture.
6. Identify technical risks.
7. Identify missing architectural decisions.
8. Identify contradictions.
9. Identify areas that may be over-engineered.
10. Identify areas that may be under-engineered.
11. Review the proposed monorepo structure.
12. Review the proposed data architecture.
13. Review the prediction architecture.
14. Review the AI architecture.
15. Review the Change Logger concept.
16. Review security considerations.
17. Review deployment assumptions.
18. Suggest improvements.

Do not silently modify the architecture.

Do not implement suggestions automatically.

The result should be an ARCHITECTURE REVIEW REPORT.

The report should contain:

## A. Strengths

## B. Critical Risks

## C. Missing Decisions

## D. Recommended Changes

## E. Questions That Must Be Resolved Before Coding

## F. Proposed Architecture After Review

## G. Suggested Phase 0 Implementation Order

The final recommendation should distinguish between:

- MUST HAVE
- SHOULD HAVE
- NICE TO HAVE
- FUTURE

The purpose of this phase is to produce a robust architecture before
implementation begins.